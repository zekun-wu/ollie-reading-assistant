import csv
import math
import json
from typing import List, Dict, Tuple
import numpy as np


class OnlineNormalizer:
    """
    Online z-score normalization using Welford's algorithm for running statistics.
    Applies log transformation to RMS feature: x_t = log(1 + RMS_t)
    """
    
    def __init__(self, n_features: int, learning_rate: float = 0.01, feature_names: List[str] = None):
        """
        Initialize online normalizer.
        
        Args:
            n_features: Number of features to normalize
            learning_rate: Learning rate for exponential moving average
            feature_names: List of feature names for applying transformations
        """
        self.n_features = n_features
        self.lr = learning_rate
        self.n = 0  # Number of observations seen
        self.mean = np.zeros(n_features)
        self.M2 = np.zeros(n_features)  # Sum of squared differences
        self.std = np.ones(n_features)  # Initialize with std=1
        self.feature_names = feature_names or []
        
    def _apply_transformations(self, x: np.ndarray) -> np.ndarray:
        """
        Apply feature-specific transformations.
        
        Args:
            x: Raw observation vector (n_features,)
            
        Returns:
            Transformed observation vector
        """
        x_transformed = x.copy()
        
        # Apply log transformation to RMS feature: x_t = log(1 + RMS_t)
        # No transformation for fixation_count (already discrete count)
        # No transformation for dwell_ratio_top_aoi (already bounded 0-1)
        if self.feature_names:
            for i, name in enumerate(self.feature_names):
                if name == 'rms_deviation' and i < len(x_transformed):
                    x_transformed[i] = np.log(1 + x_transformed[i])
                # fixation_count: no transformation needed
                # dwell_ratio_top_aoi: no transformation needed
        
        return x_transformed
    
    def update(self, x: np.ndarray):
        """
        Update running statistics with new observation.
        
        Args:
            x: New observation vector (n_features,)
        """
        # Apply transformations before updating statistics
        x_transformed = self._apply_transformations(x)
        
        self.n += 1
        
        # Update mean using exponential moving average
        self.mean = (1 - self.lr) * self.mean + self.lr * x_transformed
        
        # Update variance using Welford's algorithm
        if self.n > 1:
            delta = x_transformed - self.mean
            self.M2 = self.M2 + delta * (x_transformed - self.mean)
            self.std = np.sqrt(self.M2 / (self.n - 1))
            
        # Ensure minimum standard deviation
        self.std = np.maximum(self.std, 1e-6)
    
    def normalize(self, x: np.ndarray) -> np.ndarray:
        """
        Apply transformations and z-score normalization to observation.
        
        Args:
            x: Raw observation vector (n_features,)
            
        Returns:
            Transformed and normalized observation vector
        """
        # Apply transformations first
        x_transformed = self._apply_transformations(x)
        
        # Then normalize
        return (x_transformed - self.mean) / self.std


class OnlineHMM:
    """
    Online Hidden Markov Model with continuous (Gaussian) emissions.
    Uses cold start initialization and online EM for parameter updates.
    """
    
    def __init__(
        self,
        n_states: int = 2,
        n_features: int = 3,
        n_components: int = 2,
        learning_rate_emission: float = 0.1,
        learning_rate_transition: float = 0.05,
        learning_rate_mixture: float = 0.05,
        min_variance: float = 1e-6,
        feature_names: List[str] = None
    ):
        """
        Initialize Online HMM with GMM emissions and cold start parameters.
        
        Args:
            n_states: Number of hidden states
            n_features: Number of observation features
            n_components: Number of GMM components per state
            learning_rate_emission: Learning rate for emission parameters (μ, Σ)
            learning_rate_transition: Learning rate for transition matrix A
            learning_rate_mixture: Learning rate for mixture weights
            min_variance: Minimum variance to prevent numerical issues
            feature_names: List of feature names for transformations (e.g., ['rms_deviation'])
        """
        self.n_states = n_states
        self.n_features = n_features
        self.n_components = n_components
        self.lr_emission = learning_rate_emission
        self.lr_transition = learning_rate_transition
        self.lr_mixture = learning_rate_mixture
        self.min_variance = min_variance
        self.feature_names = feature_names or []
        
        # Feature-specific variance floor for dwell_ratio_top_aoi
        self.dwell_ratio_variance_floor = 2.5e-3
        
        # Initialize online normalizer with feature names for transformations
        self.normalizer = OnlineNormalizer(n_features, feature_names=feature_names)
        
        # Initialize transition matrix A (symmetric with preference to stay)
        self.A = np.array([
            [0.7, 0.3],
            [0.3, 0.7]
        ])
        
        # Initialize initial state distribution (uniform)
        self.pi = np.array([0.5, 0.5])
        
        # Initialize GMM parameters for each state
        self.gmm_params = {}
        
        # Base means for initialization (will be updated as data comes in)
        base_means = {
            0: np.array([0.0, 0.0, 0.0]),  # State 0: Focused
            1: np.array([0.0, 0.0, 0.0])    # State 1: Exploratory
        }
        
        for state in range(n_states):
            self.gmm_params[state] = {
                'weights': np.ones(n_components) / n_components,  # Uniform weights
                'means': {},      # {component: mean_vector}
                'covariances': {} # {component: cov_matrix}
            }
            
            # Initialize K components per state with placeholder values
            # (will be properly initialized from data in warm_start_initialization)
            for k in range(n_components):
                # Placeholder initialization - will be overwritten
                self.gmm_params[state]['means'][k] = base_means[state].copy()
                
                # Placeholder covariances (diagonal)
                self.gmm_params[state]['covariances'][k] = np.eye(n_features) * 0.1
        
        # Online tracking variables
        self.alpha_prev = None  # Previous belief state
        self.t = 0              # Current time step
        
        # History tracking
        self.state_sequence = []
        self.probability_history = []
        self.confidence_history = []
        
        print("="*80)
        print("ONLINE GMM-HMM INITIALIZED (COLD START)")
        print("="*80)
        print(f"Number of states: {n_states}")
        print(f"Number of features: {n_features}")
        print(f"Components per state: {n_components}")
        print(f"Learning rate (emission): {learning_rate_emission}")
        print(f"Learning rate (transition): {learning_rate_transition}")
        print(f"Learning rate (mixture): {learning_rate_mixture}")
        print("\nInitial Transition Matrix A:")
        print(self.A)
        print("\nGMM Structure:")
        for i in range(n_states):
            print(f"  State {i}: {n_components} components")
            for k in range(n_components):
                print(f"    Component {k}: weight={self.gmm_params[i]['weights'][k]:.3f}")
        print()
    
    def _reinitialize_gmm_parameters(self):
        """Reinitialize GMM parameters when number of features changes."""
        # Reinitialize GMM parameters for each state
        self.gmm_params = {}
        
        # Base means for initialization (will be updated as data comes in)
        base_means = {
            0: np.zeros(self.n_features),  # State 0: Focused
            1: np.zeros(self.n_features)   # State 1: Exploratory
        }
        
        for state in range(self.n_states):
            self.gmm_params[state] = {
                'weights': np.ones(self.n_components) / self.n_components,  # Uniform weights
                'means': {},      # {component: mean_vector}
                'covariances': {} # {component: cov_matrix}
            }
            
            # Initialize K components per state with placeholder values
            for k in range(self.n_components):
                # Placeholder initialization - will be overwritten from data
                self.gmm_params[state]['means'][k] = base_means[state].copy()
                
                # Placeholder covariances (diagonal)
                self.gmm_params[state]['covariances'][k] = np.eye(self.n_features) * 0.1
    
    def _initialize_gmm_from_data(self, data: np.ndarray):
        """
        Initialize GMM parameters using data statistics (deterministic).
        
        Args:
            data: Normalized data array of shape (T, n_features)
        """
        data_mean = np.mean(data, axis=0)
        data_std = np.std(data, axis=0)
        data_std = np.maximum(data_std, 1e-6)  # Prevent zero std
        
        print(f"\n=== DATA-DRIVEN GMM INITIALIZATION ===")
        print(f"Data mean: {data_mean}")
        print(f"Data std: {data_std}")
        
        for state in range(self.n_states):
            for k in range(self.n_components):
                # Deterministic initialization based on data distribution
                if state == 0:
                    # State 0: Initialize around data mean with small systematic offsets
                    if k == 0:
                        # Component 0: slightly below mean
                        offset = -data_std * 0.3
                    elif k == 1 and self.n_components > 1:
                        # Component 1: slightly above mean (only if more than 1 component)
                        offset = data_std * 0.3
                    else:
                        # Additional components: spread around mean
                        offset = data_std * (0.2 * k)
                else:
                    # State 1: Initialize around data mean with different offsets
                    if k == 0:
                        # Component 0: at data mean
                        offset = np.zeros(self.n_features)
                    elif k == 1 and self.n_components > 1:
                        # Component 1: further from mean (only if more than 1 component)
                        offset = data_std * 0.6
                    else:
                        # Additional components: spread around mean
                        offset = data_std * (0.4 * k)
                
                self.gmm_params[state]['means'][k] = data_mean + offset
                
                # Initialize covariances based on data variance
                self.gmm_params[state]['covariances'][k] = np.diag(data_std**2 * 0.5)
        
        print("\nInitialized GMM parameters from data:")
        for state in range(self.n_states):
            print(f"  State {state}:")
            for k in range(self.n_components):
                print(f"    Component {k}: mean={self.gmm_params[state]['means'][k]}")
    
    def warm_start_initialization(self, data: List[Dict], warm_start_segments: int = 8, em_iterations: int = 10):
        """
        Run batch EM algorithm on first K segments to learn initial parameters.
        
        Args:
            data: List of feature dictionaries
            warm_start_segments: Number of segments for warm start
            em_iterations: Number of EM iterations to run
        """
        print(f"\nWarm Start: Running batch EM on first {warm_start_segments} segments for {em_iterations} iterations...")
        
        # 1. Extract and normalize warm start data (two-pass approach)
        # First pass: Extract raw features and update normalizer statistics
        raw_warm_data = []
        
        # Use ONLY the feature_names configured during HMM initialization
        # Do NOT auto-detect features from data (that was causing the 3-feature bug)
        feature_names = self.feature_names if hasattr(self, 'feature_names') and self.feature_names else ['dwell_ratio_top_aoi']
        
        print(f"Using configured features: {feature_names}")
        print(f"Number of features: {len(feature_names)}")
        
        # Verify n_features matches (should already be correct from __init__)
        if len(feature_names) != self.n_features:
            print(f"WARNING: Feature count mismatch! Configured: {len(feature_names)}, HMM: {self.n_features}")
        
        for i in range(min(warm_start_segments, len(data))):
            row = data[i]
            # Extract ONLY the configured features (not all available features)
            raw_features = []
            for fname in feature_names:
                if fname in row:
                    raw_features.append(row[fname])
                else:
                    raw_features.append(0.0)  # Default if missing
            
            raw_features = np.array(raw_features)
            raw_warm_data.append(raw_features)
            self.normalizer.update(raw_features)

        # Second pass: Normalize all data with complete statistics
        warm_data = []
        for raw_features in raw_warm_data:
            warm_data.append(self.normalizer.normalize(raw_features))

        warm_data = np.array(warm_data)
        T = len(warm_data)
        
        # Initialize GMM parameters from actual data (deterministic)
        self._initialize_gmm_from_data(warm_data)
        
        # DEBUG: Verify normalization statistics
        print(f"\n=== NORMALIZATION STATISTICS ===")
        print(f"Normalizer mean: {self.normalizer.mean}")
        print(f"Normalizer std: {self.normalizer.std}")
        print(f"Number of observations used: {self.normalizer.n}")
        
        # Reset debug flags for fresh analysis
        if hasattr(self, '_debug_gmm_called'):
            delattr(self, '_debug_gmm_called')
        
        # DEBUG: Analyze warm start data distribution
        print(f"\n=== DATA DISTRIBUTION ANALYSIS ===")
        print(f"Warm data shape: {warm_data.shape}")
        print(f"Data range per feature:")
        for feat in range(warm_data.shape[1]):
            print(f"  Feature {feat}: min={warm_data[:, feat].min():.3f}, max={warm_data[:, feat].max():.3f}")
        print(f"Data mean: {warm_data.mean(axis=0)}")
        print(f"Data std: {warm_data.std(axis=0)}")
        
        # DEBUG: Print initial GMM parameters before EM
        print("\nInitial GMM parameters before EM:")
        for state in range(self.n_states):
            print(f"  State {state}:")
            for k in range(self.n_components):
                print(f"    Component {k}: weight={self.gmm_params[state]['weights'][k]:.3f}")
                print(f"      Mean: {self.gmm_params[state]['means'][k]}")
                print(f"      Variance (diag): {np.diag(self.gmm_params[state]['covariances'][k])}")
        
        # DEBUG: Check GMM initialization sanity
        print(f"\n=== GMM INITIALIZATION CHECK ===")
        data_mean = warm_data.mean(axis=0)
        for state in range(self.n_states):
            for k in range(self.n_components):
                mean = self.gmm_params[state]['means'][k]
                mean_distance = np.linalg.norm(mean - data_mean)
                print(f"  State {state}, Comp {k}: distance from data mean = {mean_distance:.3f}")
                if np.any(np.abs(mean) > 10):
                    print(f"    WARNING: Initial mean {mean} seems extreme!")
        
        # 2. Run Baum-Welch EM algorithm
        for iteration in range(em_iterations):
            # E-step: Forward-backward algorithm
            alpha, c = self._forward_algorithm(warm_data)  # Now returns (alpha, c)
            beta = self._backward_algorithm(warm_data, c)  # Now takes c as parameter
            gamma, xi = self._compute_posteriors(warm_data, alpha, beta)
            
            # M-step: Update all parameters
            self._update_gmm_from_batch(warm_data, gamma)
            self._update_transition_from_batch(xi)
            self._update_prior_from_batch(gamma)
            
            # Show key parameters on first and last iteration only
            if iteration == 0 or iteration == em_iterations - 1:
                print(f"\n  Iteration {iteration+1} - Key Parameters:")
                for state in range(self.n_states):
                    for k in range(self.n_components):
                        print(f"    GMM State {state}, Comp {k}: mean={self.gmm_params[state]['means'][k]}, weight={self.gmm_params[state]['weights'][k]:.3f}")
            
            # Compute log-likelihood to track convergence
            log_likelihood = self._compute_log_likelihood(warm_data, c)  # Now uses c
            print(f"  Iteration {iteration+1}: log-likelihood = {log_likelihood:.2f}")
        
        print("Batch EM warm start complete!")
        print(f"Final transition matrix:\n{self.A}")
        print(f"Final prior: {self.pi}")
        print(f"Normalizer stats: mean={self.normalizer.mean}, std={self.normalizer.std}")
        
        # DEBUG: Print final GMM parameters after EM
        print("\nFinal GMM parameters after EM:")
        for state in range(self.n_states):
            print(f"\n  State {state}:")
            for k in range(self.n_components):
                print(f"    Component {k}:")
                print(f"      Weight: {self.gmm_params[state]['weights'][k]:.3f}")
                print(f"      Mean: {self.gmm_params[state]['means'][k]}")
                print(f"      Variance (diag): {np.diag(self.gmm_params[state]['covariances'][k])}")
    
    def _gmm_emission_probability(self, x: np.ndarray, state: int) -> float:
        """
        Compute P(x | state) using Gaussian Mixture Model.
        
        P(x | state) = Σ(k=1 to K) π_k * N(x; μ_k, Σ_k)
        
        Args:
            x: Observation vector (n_features,)
            state: State index
            
        Returns:
            Emission probability
        """
        total_prob = 0.0
        
        for k in range(self.n_components):
            # Get component parameters
            weight = self.gmm_params[state]['weights'][k]
            mean = self.gmm_params[state]['means'][k]
            cov = self.gmm_params[state]['covariances'][k]
            
            # Compute multivariate Gaussian probability
            diff = x - mean
            
            # Add numerical stability to covariance matrix
            cov_stable = cov + np.eye(self.n_features) * 1e-6
            
            try:
                # Compute log probability using proper multivariate formula
                # log N(x; μ, Σ) = -0.5 * (x-μ)ᵀ Σ⁻¹ (x-μ) - 0.5 * log|Σ| - 0.5 * d * log(2π)
                log_prob = -0.5 * np.dot(diff, np.linalg.solve(cov_stable, diff))
                log_prob += -0.5 * np.linalg.slogdet(cov_stable)[1]  # log determinant
                log_prob += -0.5 * self.n_features * math.log(2 * math.pi)
                
                # Clip log_prob to prevent overflow/underflow
                log_prob = np.clip(log_prob, -700, 700)
                gaussian_prob = math.exp(log_prob)
            except:
                gaussian_prob = 1e-10
            
            total_prob += weight * gaussian_prob
        
        return max(total_prob, 1e-10)  # Prevent zero emission probabilities
    
    def _compute_component_responsibilities(self, x: np.ndarray, state: int) -> np.ndarray:
        """
        Compute responsibility (posterior) of each component for observation x.
        
        γ_k = π_k * N(x; μ_k, Σ_k) / P(x | state)
        
        Args:
            x: Observation vector
            state: State index
            
        Returns:
            responsibilities: array of size n_components
        """
        responsibilities = np.zeros(self.n_components)
        
        for k in range(self.n_components):
            weight = self.gmm_params[state]['weights'][k]
            mean = self.gmm_params[state]['means'][k]
            cov = self.gmm_params[state]['covariances'][k]
            
            # Compute multivariate Gaussian probability
            diff = x - mean
            
            # Add numerical stability to covariance matrix
            cov_stable = cov + np.eye(self.n_features) * 1e-6
            
            try:
                # Compute log probability using proper multivariate formula
                log_prob = -0.5 * np.dot(diff, np.linalg.solve(cov_stable, diff))
                log_prob += -0.5 * np.linalg.slogdet(cov_stable)[1]
                log_prob += -0.5 * self.n_features * math.log(2 * math.pi)
                
                # Clip log_prob to prevent overflow/underflow
                log_prob = np.clip(log_prob, -700, 700)
                gaussian_prob = math.exp(log_prob)
            except:
                gaussian_prob = 1e-10
            
            responsibilities[k] = weight * gaussian_prob
        
        # Normalize responsibilities
        total = responsibilities.sum()
        if total > 0:
            responsibilities = responsibilities / total
        else:
            responsibilities = np.ones(self.n_components) / self.n_components
        
        return responsibilities
    
    def _forward_algorithm(self, observations: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute forward probabilities with scaling for batch EM.
        
        Args:
            observations: Array of shape (T, n_features)
            
        Returns:
            alpha: Scaled forward probabilities (T, n_states)
            c: Scaling factors (T,)
        """
        T = len(observations)
        alpha = np.zeros((T, self.n_states))
        c = np.zeros(T)  # Scaling factors
        
        # Initialize alpha[0]
        for i in range(self.n_states):
            alpha[0, i] = self.pi[i] * self._gmm_emission_probability(observations[0], i)
        
        # Scale first time step
        c[0] = np.sum(alpha[0, :])
        if c[0] > 0:
            alpha[0, :] /= c[0]
        else:
            alpha[0, :] = 1.0 / self.n_states  # Uniform if zero
            c[0] = 1.0
        
        # Forward recursion with scaling
        for t in range(1, T):
            for j in range(self.n_states):
                alpha[t, j] = 0
                for i in range(self.n_states):
                    alpha[t, j] += alpha[t-1, i] * self.A[i, j]
                alpha[t, j] *= self._gmm_emission_probability(observations[t], j)
            
            # Scale to prevent underflow
            c[t] = np.sum(alpha[t, :])
            if c[t] > 0:
                alpha[t, :] /= c[t]
            else:
                alpha[t, :] = 1.0 / self.n_states  # Uniform if zero
                c[t] = 1.0
        
        return alpha, c
    
    def _backward_algorithm(self, observations: np.ndarray, c: np.ndarray) -> np.ndarray:
        """
        Compute backward probabilities with scaling for batch EM.
        
        Args:
            observations: Array of shape (T, n_features)
            c: Scaling factors from forward algorithm (T,)
            
        Returns:
            beta: Scaled backward probabilities (T, n_states)
        """
        T = len(observations)
        beta = np.zeros((T, self.n_states))
        
        # Initialize beta[T-1] - scaled by c[T-1]
        beta[T-1, :] = 1.0 / c[T-1] if c[T-1] > 0 else 1.0
        
        # Backward recursion with same scaling as forward
        for t in range(T-2, -1, -1):
            for i in range(self.n_states):
                beta[t, i] = 0
                for j in range(self.n_states):
                    beta[t, i] += self.A[i, j] * self._gmm_emission_probability(observations[t+1], j) * beta[t+1, j]
            
            # Scale using same factors as forward algorithm
            if c[t] > 0:
                beta[t, :] /= c[t]
        
        return beta
    
    def _compute_posteriors(self, observations: np.ndarray, alpha: np.ndarray, beta: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute gamma (state posteriors) and xi (transition posteriors) for batch EM.
        
        Args:
            observations: Array of shape (T, n_features)
            alpha: Forward probabilities (T, n_states)
            beta: Backward probabilities (T, n_states)
            
        Returns:
            gamma: State posteriors (T, n_states)
            xi: Transition posteriors (T-1, n_states, n_states)
        """
        T = len(observations)
        
        # Compute gamma (state posteriors)
        gamma = np.zeros((T, self.n_states))
        for t in range(T):
            total = np.sum(alpha[t, :] * beta[t, :])
            if total > 0:
                gamma[t, :] = (alpha[t, :] * beta[t, :]) / total
            else:
                gamma[t, :] = 1.0 / self.n_states
        
        # Compute xi (transition posteriors)
        xi = np.zeros((T-1, self.n_states, self.n_states))
        for t in range(T-1):
            total = 0
            for i in range(self.n_states):
                for j in range(self.n_states):
                    xi[t, i, j] = alpha[t, i] * self.A[i, j] * self._gmm_emission_probability(observations[t+1], j) * beta[t+1, j]
                    total += xi[t, i, j]
            
            if total > 0:
                xi[t, :, :] /= total
            else:
                xi[t, :, :] = 1.0 / (self.n_states * self.n_states)
        
        return gamma, xi
    
    def _compute_log_likelihood(self, observations: np.ndarray, c: np.ndarray) -> float:
        """
        Compute log-likelihood using scaling factors.
        
        Args:
            observations: Array of shape (T, n_features)
            c: Scaling factors from forward algorithm (T,)
            
        Returns:
            Log-likelihood
        """
        # Log-likelihood is the sum of log scaling factors
        log_likelihood = 0.0
        for t in range(len(c)):
            if c[t] > 0:
                log_likelihood += np.log(c[t])
        
        return log_likelihood
    
    def _update_gmm_from_batch(self, observations: np.ndarray, gamma: np.ndarray):
        """
        Update GMM parameters using batch EM statistics.
        
        Args:
            observations: Array of shape (T, n_features)
            gamma: State posteriors (T, n_states)
        """
        T = len(observations)
        
        # DEBUG: Analyze GMM responsibilities (first call only)
        if not hasattr(self, '_debug_gmm_called'):
            self._debug_gmm_called = True
            print(f"\n=== GMM UPDATE DEBUG (First EM Iteration) ===")
            for state_debug in range(self.n_states):
                # Compute responsibilities for debugging
                responsibilities_debug = np.zeros((T, self.n_components))
                for t in range(T):
                    for k in range(self.n_components):
                        weight = self.gmm_params[state_debug]['weights'][k]
                        mean = self.gmm_params[state_debug]['means'][k]
                        cov = self.gmm_params[state_debug]['covariances'][k]
                        cov_stable = cov + np.eye(self.n_features) * 1e-6
                        diff = observations[t] - mean
                        try:
                            log_prob = -0.5 * np.dot(diff, np.linalg.solve(cov_stable, diff))
                            log_prob += -0.5 * np.linalg.slogdet(cov_stable)[1]
                            log_prob += -0.5 * self.n_features * math.log(2 * math.pi)
                            log_prob = np.clip(log_prob, -700, 700)
                            gaussian_prob = math.exp(log_prob)
                        except:
                            gaussian_prob = 1e-10
                        responsibilities_debug[t, k] = weight * gaussian_prob
                
                # Normalize
                for t in range(T):
                    total = np.sum(responsibilities_debug[t, :])
                    if total > 0:
                        responsibilities_debug[t, :] /= total
                
                print(f"\n  State {state_debug}:")
                print(f"    Gamma sum: {np.sum(gamma[:, state_debug]):.3f}")
                for k in range(self.n_components):
                    total_resp = np.sum(gamma[:, state_debug] * responsibilities_debug[:, k])
                    print(f"    Component {k}:")
                    print(f"      Total responsibility: {total_resp:.6f}")
                    print(f"      Current weight: {self.gmm_params[state_debug]['weights'][k]:.3f}")
                    print(f"      Current mean: {self.gmm_params[state_debug]['means'][k]}")
                    
                    # Show what the update will be
                    if total_resp > 0:
                        weighted_obs = np.sum(gamma[:, state_debug].reshape(-1, 1) * responsibilities_debug[:, k].reshape(-1, 1) * observations, axis=0)
                        new_mean = weighted_obs / total_resp
                        print(f"      New mean will be: {new_mean}")
                        if np.any(np.abs(new_mean) > 10):
                            print(f"        ⚠️  WARNING: Mean will become EXTREME!")
        
        for state in range(self.n_states):
            # Compute component responsibilities for this state
            responsibilities = np.zeros((T, self.n_components))
            
            for t in range(T):
                for k in range(self.n_components):
                    weight = self.gmm_params[state]['weights'][k]
                    mean = self.gmm_params[state]['means'][k]
                    cov = self.gmm_params[state]['covariances'][k]
                    
                    # Compute multivariate Gaussian probability
                    diff = observations[t] - mean
                    
                    # Add numerical stability to covariance matrix
                    cov_stable = cov + np.eye(self.n_features) * 1e-6
                    
                    try:
                        # Compute log probability using proper multivariate formula
                        log_prob = -0.5 * np.dot(diff, np.linalg.solve(cov_stable, diff))
                        log_prob += -0.5 * np.linalg.slogdet(cov_stable)[1]
                        log_prob += -0.5 * self.n_features * math.log(2 * math.pi)
                        
                        # Clip log_prob to prevent overflow/underflow
                        log_prob = np.clip(log_prob, -700, 700)
                        gaussian_prob = math.exp(log_prob)
                    except:
                        gaussian_prob = 1e-10
                    
                    responsibilities[t, k] = weight * gaussian_prob
            
            # Normalize responsibilities
            for t in range(T):
                total = np.sum(responsibilities[t, :])
                if total > 0:
                    responsibilities[t, :] /= total
                else:
                    responsibilities[t, :] = 1.0 / self.n_components
            
            # Update each component
            for k in range(self.n_components):
                # Compute weighted statistics
                total_resp = np.sum(gamma[:, state] * responsibilities[:, k])
                
                if total_resp > 0:
                    # Update component mean
                    weighted_obs = np.sum(gamma[:, state].reshape(-1, 1) * responsibilities[:, k].reshape(-1, 1) * observations, axis=0)
                    self.gmm_params[state]['means'][k] = weighted_obs / total_resp
                    
                    # Update component covariance
                    diff = observations - self.gmm_params[state]['means'][k]
                    weighted_diff = np.sum(gamma[:, state].reshape(-1, 1) * responsibilities[:, k].reshape(-1, 1) * diff**2, axis=0)
                    # Apply feature-specific variance floor for dwell_ratio_top_aoi (index 0)
                    variance_floors = np.array([self.dwell_ratio_variance_floor if ('dwell_ratio_top_aoi' in self.feature_names and i == 0) else self.min_variance 
                                                for i in range(self.n_features)])
                    self.gmm_params[state]['covariances'][k] = np.diag(np.maximum(weighted_diff / total_resp, variance_floors))
                    
                    # Update component weight
                    self.gmm_params[state]['weights'][k] = total_resp / np.sum(gamma[:, state])
                else:
                    # Keep current parameters if no responsibility
                    pass
            
            # Renormalize mixture weights
            total_weight = np.sum(self.gmm_params[state]['weights'])
            if total_weight > 0:
                self.gmm_params[state]['weights'] = self.gmm_params[state]['weights'] / total_weight
    
    def _update_transition_from_batch(self, xi: np.ndarray):
        """
        Update transition matrix using batch EM statistics.
        
        Args:
            xi: Transition posteriors (T-1, n_states, n_states)
        """
        T_minus_1 = len(xi)
        
        for i in range(self.n_states):
            total_from_i = 0
            for j in range(self.n_states):
                self.A[i, j] = np.sum(xi[:, i, j])
                total_from_i += self.A[i, j]
            
            # Normalize transition probabilities
            if total_from_i > 0:
                self.A[i, :] = self.A[i, :] / total_from_i
            else:
                self.A[i, :] = 1.0 / self.n_states
    
    def _update_prior_from_batch(self, gamma: np.ndarray):
        """
        Update prior distribution using batch EM statistics.
        
        Args:
            gamma: State posteriors (T, n_states)
        """
        # Use first time step posteriors as prior
        if len(gamma) > 0:
            self.pi = gamma[0, :].copy()
            
            # Normalize
            total = np.sum(self.pi)
            if total > 0:
                self.pi = self.pi / total
            else:
                self.pi = np.ones(self.n_states) / self.n_states
        else:
            self.pi = np.ones(self.n_states) / self.n_states
    
    def _forward_step(self, x: np.ndarray) -> np.ndarray:
        """
        Perform forward step (filtering) to compute α_t = P(state_t | x_1:t).
        
        Args:
            x: Current observation
            
        Returns:
            alpha_t: Belief state distribution (n_states,)
        """
        alpha_raw = np.zeros(self.n_states)
        
        if self.t == 0:
            # First observation: use initial distribution
            for i in range(self.n_states):
                alpha_raw[i] = self.pi[i] * self._gmm_emission_probability(x, i)
        else:
            # Subsequent observations: use transition probabilities
            for j in range(self.n_states):  # To state j
                transition_sum = sum(
                    self.alpha_prev[i] * self.A[i, j] 
                    for i in range(self.n_states)
                )
                alpha_raw[j] = transition_sum * self._gmm_emission_probability(x, j)
        
        # Normalize to get probabilities
        total = alpha_raw.sum()
        if total > 0:
            alpha_t = alpha_raw / total
        else:
            # Fallback to uniform if numerical issues
            alpha_t = np.ones(self.n_states) / self.n_states
        
        return alpha_t
    
    def _predict_state(self, alpha_t: np.ndarray) -> Tuple[int, float]:
        """
        Predict most likely state from belief distribution.
        
        Args:
            alpha_t: Belief state distribution
            
        Returns:
            (predicted_state, confidence)
        """
        predicted_state = int(np.argmax(alpha_t))
        confidence = float(np.max(alpha_t))
        
        return predicted_state, confidence
    
    def _update_parameters(self, x: np.ndarray, alpha_t: np.ndarray, predicted_state: int):
        """
        Update GMM parameters using online EM approximation.
        
        Args:
            x: Current observation
            alpha_t: Current belief state
            predicted_state: Predicted state for this time step
        """
        # 1. Update GMM parameters for each state
        for state in range(self.n_states):
            # Weight by state probability (soft assignment)
            state_weight = alpha_t[state]
            lr = self.lr_emission * state_weight
            
            # Compute component responsibilities
            responsibilities = self._compute_component_responsibilities(x, state)
            
            # Update each component
            for k in range(self.n_components):
                comp_weight = responsibilities[k]
                comp_lr = lr * comp_weight
                
                # Update component mean
                mean = self.gmm_params[state]['means'][k]
                diff = x - mean
                self.gmm_params[state]['means'][k] = mean + comp_lr * diff
                
                # Update component covariance
                cov = self.gmm_params[state]['covariances'][k]
                for j in range(self.n_features):
                    cov[j, j] = (1 - comp_lr) * cov[j, j] + comp_lr * diff[j]**2
                    # Apply feature-specific variance floor for dwell_ratio_top_aoi (index 0)
                    if j == 0 and 'dwell_ratio_top_aoi' in self.feature_names:
                        cov[j, j] = max(cov[j, j], self.dwell_ratio_variance_floor)
                    else:
                        cov[j, j] = max(cov[j, j], self.min_variance)
                
                # Update component weight
                weight_lr = self.lr_mixture * state_weight
                old_weight = self.gmm_params[state]['weights'][k]
                self.gmm_params[state]['weights'][k] = (1 - weight_lr) * old_weight + weight_lr * comp_weight
            
            # Renormalize mixture weights
            total_weight = self.gmm_params[state]['weights'].sum()
            if total_weight > 0:
                self.gmm_params[state]['weights'] = self.gmm_params[state]['weights'] / total_weight
        
        # 2. Update transition matrix (if t > 0)
        if self.t > 0:
            # Get previous predicted state
            prev_state = self.state_sequence[-1]
            curr_state = predicted_state
            
            # Update transition counts with learning rate
            lr_A = self.lr_transition
            for i in range(self.n_states):
                for j in range(self.n_states):
                    if i == prev_state and j == curr_state:
                        # Reinforce observed transition
                        self.A[i, j] = (1 - lr_A) * self.A[i, j] + lr_A * 1.0
                    else:
                        # Decay other transitions
                        self.A[i, j] = (1 - lr_A) * self.A[i, j]
            
            # Normalize rows to maintain probability constraints
            for i in range(self.n_states):
                row_sum = self.A[i, :].sum()
                if row_sum > 0:
                    self.A[i, :] = self.A[i, :] / row_sum
    
    def fit_online_step(self, x: np.ndarray) -> Dict:
        """
        Process one observation and return predicted state.
        This is the main online learning function.
        
        Args:
            x: Observation vector (n_features,)
            
        Returns:
            Dictionary with prediction results
        """
        # Step 1: Forward pass (filtering)
        alpha_t = self._forward_step(x)
        
        # Step 2: Predict state
        predicted_state, confidence = self._predict_state(alpha_t)
        
        # Step 3: Update parameters
        self._update_parameters(x, alpha_t, predicted_state)
        
        # Step 4: Store for next iteration
        self.alpha_prev = alpha_t.copy()
        self.state_sequence.append(predicted_state)
        self.probability_history.append(alpha_t.copy())
        self.confidence_history.append(confidence)
        self.t += 1
        
        return {
            'state': predicted_state,
            'confidence': confidence,
            'state_probs': alpha_t,
            'time_step': self.t - 1
        }
    
    def get_learned_parameters(self) -> Dict:
        """
        Get current learned GMM parameters.
        
        Returns:
            Dictionary with all model parameters
        """
        gmm_data = {}
        for state in range(self.n_states):
            gmm_data[state] = {
                'weights': self.gmm_params[state]['weights'].tolist(),
                'means': {k: mean.tolist() for k, mean in self.gmm_params[state]['means'].items()},
                'covariances': {k: np.diag(cov).tolist() for k, cov in self.gmm_params[state]['covariances'].items()}
            }
        
        return {
            'transition_matrix': self.A.tolist(),
            'gmm_parameters': gmm_data,
            'n_components_per_state': self.n_components,
            'normalizer_stats': {
                'mean': self.normalizer.mean.tolist(),
                'std': self.normalizer.std.tolist(),
                'n_observations': self.normalizer.n
            }
        }


def normalize_features(row: Dict, normalizer: OnlineNormalizer) -> np.ndarray:
    """
    Normalize features using online z-score normalization.
    
    Args:
        row: Dictionary with raw features
        normalizer: OnlineNormalizer instance
        
    Returns:
        Normalized feature vector
    """
    # Extract features dynamically based on available keys
    raw_features = []
    
    # Check which features are available in the data
    if 'rms_deviation' in row:
        raw_features.append(row['rms_deviation'])
    if 'fixation_count' in row:
        raw_features.append(row['fixation_count'])
    if 'dwell_ratio_top_aoi' in row:
        raw_features.append(row['dwell_ratio_top_aoi'])
    
    raw_features = np.array(raw_features)
    
    # Update normalizer statistics
    normalizer.update(raw_features)
    
    # Apply z-score normalization
    return normalizer.normalize(raw_features)


def load_gaze_features(csv_path: str) -> List[Dict]:
    """
    Load gaze features from CSV file.
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        List of feature dictionaries
    """
    data = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({
                'segment_index': int(row['segment_index']),
                'start_time': float(row['start_time']),
                'end_time': float(row['end_time']),
                'rms_deviation': float(row['rms_deviation']),
                'fixation_count': int(row['fixation_count']),
                'dwell_ratio_top_aoi': float(row['dwell_ratio_top_aoi'])
            })
    return data


def run_online_hmm_analysis(
    csv_path: str = 'gaze_metrics_pygaze_results.csv',
    learning_rate_emission: float = 0.1,
    learning_rate_transition: float = 0.05,
    warm_start_segments: int = 8,
    em_iterations: int = 10
) -> Tuple[List[Dict], OnlineHMM]:
    """
    Main function to run online HMM analysis on gaze features.
    
    Args:
        csv_path: Path to gaze features CSV
        learning_rate_emission: Learning rate for Gaussian parameters
        learning_rate_transition: Learning rate for transition matrix
        warm_start_segments: Number of segments to use for warm start initialization
        em_iterations: Number of EM iterations for batch warm start
        
    Returns:
        (results, hmm_model)
    """
    print("="*80)
    print("ONLINE HMM GAZE ANALYSIS")
    print("="*80)
    
    # Load data
    print(f"\nLoading gaze features from: {csv_path}")
    data = load_gaze_features(csv_path)
    print(f"Loaded {len(data)} segments")
    
    # Initialize HMM with GMM
    hmm = OnlineHMM(
        n_states=2,
        n_features=3,
        n_components=2,
        learning_rate_emission=learning_rate_emission,
        learning_rate_transition=learning_rate_transition,
        learning_rate_mixture=0.05
    )
    
    # WARM START: Initialize with first K segments if available
    if warm_start_segments > 0 and len(data) >= warm_start_segments:
        hmm.warm_start_initialization(data, warm_start_segments, em_iterations)
    
    # Process each segment sequentially (online learning)
    print("\nProcessing segments online...")
    results = []
    
    for i, row in enumerate(data):
        # Skip warm start segments - they were already used for initialization
        if i < warm_start_segments:
            continue
        
        # Normalize features using online z-score normalization
        x_t = normalize_features(row, hmm.normalizer)
        
        # Online learning step
        prediction = hmm.fit_online_step(x_t)
        
        # Store result
        results.append({
            'segment_index': row['segment_index'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
            'predicted_state': prediction['state'],
            'state_0_prob': float(prediction['state_probs'][0]),
            'state_1_prob': float(prediction['state_probs'][1]),
            'confidence': prediction['confidence'],
            'raw_features': {
                'rms_deviation': row['rms_deviation'],
                'fixation_count': row['fixation_count'],
                'dwell_ratio_top_aoi': row['dwell_ratio_top_aoi']
            },
            'normalized_features': x_t.tolist()
        })
        
        # Print progress every 10 segments (only for segments after warm start)
        if (i >= warm_start_segments) and ((i - warm_start_segments + 1) % 10 == 0):
            processed = i - warm_start_segments + 1
            remaining = len(data) - warm_start_segments
            print(f"  Processed {processed}/{remaining} segments...")
    
    actual_processed = len(data) - warm_start_segments
    print(f"Completed processing {actual_processed} segments (after {warm_start_segments} warm start segments)")
    
    # Summary statistics
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    
    state_counts = {0: 0, 1: 0}
    for r in results:
        state_counts[r['predicted_state']] += 1
    
    print(f"\nState Distribution (online learning phase):")
    print(f"  State 0: {state_counts[0]} segments ({state_counts[0]/len(results)*100:.1f}%)")
    print(f"  State 1: {state_counts[1]} segments ({state_counts[1]/len(results)*100:.1f}%)")
    print(f"  Total predictions: {len(results)} (from segment {warm_start_segments} onwards)")
    
    avg_confidence = sum(r['confidence'] for r in results) / len(results)
    print(f"\nAverage Confidence: {avg_confidence:.3f}")
    
    # Show learned parameters
    print("\n" + "="*80)
    print("LEARNED PARAMETERS")
    print("="*80)
    
    print("\nFinal Transition Matrix A:")
    print(hmm.A)
    print("Interpretation:")
    print(f"  P(stay in State 0) = {hmm.A[0,0]:.3f}")
    print(f"  P(0->1 transition) = {hmm.A[0,1]:.3f}")
    print(f"  P(1->0 transition) = {hmm.A[1,0]:.3f}")
    print(f"  P(stay in State 1) = {hmm.A[1,1]:.3f}")
    
    print("\nFinal GMM Parameters:")
    feature_names = ['RMS', 'FixCount', 'DwellRatio']
    for i in range(2):
        print(f"  State {i}:")
        for k in range(hmm.n_components):
            print(f"    Component {k} (weight: {hmm.gmm_params[i]['weights'][k]:.3f}):")
            mean = hmm.gmm_params[i]['means'][k]
            cov_diag = np.diag(hmm.gmm_params[i]['covariances'][k])
        for j, name in enumerate(feature_names):
                print(f"      {name}: μ={mean[j]:.3f}, σ²={cov_diag[j]:.6f}")
    
    print(f"\nNormalizer Statistics:")
    print(f"  Mean: {hmm.normalizer.mean}")
    print(f"  Std: {hmm.normalizer.std}")
    print(f"  Observations: {hmm.normalizer.n}")
    
    # State interpretation
    print("\n" + "="*80)
    print("STATE INTERPRETATION")
    print("="*80)
    
    for i in range(2):
        print(f"\nState {i} characteristics:")
        # Use weighted average of components for interpretation
        weighted_mean = np.zeros(3)
        for k in range(hmm.n_components):
            weighted_mean += hmm.gmm_params[i]['weights'][k] * hmm.gmm_params[i]['means'][k]
        
        print(f"  RMS Deviation: {'HIGH' if weighted_mean[0] > 0 else 'LOW'} ({weighted_mean[0]:.3f} std)")
        print(f"  Fixation Count: {'HIGH' if weighted_mean[1] > 0 else 'LOW'} ({weighted_mean[1]:.3f} std)")
        print(f"  Dwell Ratio: {'HIGH' if weighted_mean[2] > 0 else 'LOW'} ({weighted_mean[2]:.3f} std)")
        
        # Infer cognitive state based on weighted mean
        if weighted_mean[0] < 0 and weighted_mean[1] > 0 and weighted_mean[2] > 0:
            print(f"  --> Likely: FOCUSED/READING state")
        elif weighted_mean[0] > 0 and weighted_mean[1] < 0:
            print(f"  --> Likely: EXPLORATORY/SEARCHING state")
        else:
            print(f"  --> Mixed characteristics")
        
        # Show component details
        for k in range(hmm.n_components):
            comp_mean = hmm.gmm_params[i]['means'][k]
            comp_weight = hmm.gmm_params[i]['weights'][k]
            print(f"    Component {k} (weight: {comp_weight:.3f}): RMS={comp_mean[0]:.3f}, Fix={comp_mean[1]:.3f}, Dwell={comp_mean[2]:.3f}")
    
    return results, hmm


def save_results(results: List[Dict], hmm: OnlineHMM, output_prefix: str = 'hmm'):
    """
    Save results to CSV and JSON files.
    
    Args:
        results: List of prediction results
        hmm: Trained HMM model
        output_prefix: Prefix for output files
    """
    # Save state predictions to CSV
    csv_path = f'{output_prefix}_state_predictions.csv'
    with open(csv_path, 'w', newline='') as f:
        fieldnames = ['segment_index', 'start_time', 'end_time', 'predicted_state', 
                      'state_0_prob', 'state_1_prob', 'confidence']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fieldnames})
    
    print(f"\n[SUCCESS] State predictions saved to: {csv_path}")
    
    # Save learned parameters to JSON
    json_path = f'{output_prefix}_learned_parameters.json'
    params = hmm.get_learned_parameters()
    params['state_sequence'] = hmm.state_sequence
    params['n_segments'] = len(results)
    
    with open(json_path, 'w') as f:
        json.dump(params, f, indent=2)
    
    print(f"[SUCCESS] Learned parameters saved to: {json_path}")
    
    # Save detailed results with features
    detailed_path = f'{output_prefix}_detailed_results.json'
    with open(detailed_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"[SUCCESS] Detailed results saved to: {detailed_path}")


# Execute the analysis
if __name__ == "__main__":
    # Run online HMM analysis with warm start
    results, hmm_model = run_online_hmm_analysis(
        csv_path='gaze_metrics_pygaze_results.csv',
        learning_rate_emission=0.1,
        learning_rate_transition=0.05,
        warm_start_segments=16,
        em_iterations=10
    )
    
    # Save results
    save_results(results, hmm_model, output_prefix='hmm')
    
    # Print first 10 predictions
    print("\n" + "="*80)
    print("FIRST 10 PREDICTIONS")
    print("="*80)
    for i, r in enumerate(results[:10]):
        print(f"\nSegment {i} ({r['start_time']:.1f}-{r['end_time']:.1f} ms):")
        print(f"  Predicted State: {r['predicted_state']}")
        print(f"  Confidence: {r['confidence']:.3f}")
        print(f"  P(State 0): {r['state_0_prob']:.3f}, P(State 1): {r['state_1_prob']:.3f}")
        print(f"  Features: RMS={r['raw_features']['rms_deviation']:.1f}px, "
              f"FixCount={r['raw_features']['fixation_count']}, "
              f"Dwell={r['raw_features']['dwell_ratio_top_aoi']:.2f}")

