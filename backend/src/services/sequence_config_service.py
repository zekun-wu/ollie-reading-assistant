"""
Sequence Configuration Service
Manages predefined sequence configurations for reading sessions (Storytelling only)
"""
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SequenceConfigService:
    """Service for managing predefined sequence configurations (Storytelling only)"""
    
    def __init__(self):
        """Initialize with predefined sequences"""
        # Available storytelling images (9 total)
        self.storytelling_images = ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg', '6.jpg', '7.png', '8.png', '9.png']        
        # Define predefined sequences
        self.sequences = self._define_sequences()
        
        # Participant files directory
        backend_dir = Path(__file__).parent.parent.parent
        self.participants_dir = backend_dir / "participants"
        
        logger.info("Sequence Config Service initialized (Storytelling only)")
    
    def _define_sequences(self) -> Dict[str, Dict]:
        """
        Define predefined sequence configurations (Storytelling only)
        Distributes 6 storytelling images across 2 conditions (assistance, eye_assistance)
        
        Returns:
            Dictionary mapping sequence IDs to configuration dicts
        """
        sequences = {
            "default": {
                "condition_order": ["eye_assistance", "assistance"],
                "assistance": ["9.png", "4.jpg", "8.png"],
                "eye_assistance": ["3.jpg", "6.jpg", "7.png"]
            }
        }
        return sequences
    
    def _flatten_sequence(self, config: Dict) -> List[Dict]:
        """
        Flatten a grouped sequence configuration into a flat list of steps (Storytelling only)
        
        Args:
            config: Configuration dict with condition_order and condition image lists
            
        Returns:
            List of sequence steps with numbered step values
        """
        flat_sequence = []
        step_number = 1
        
        condition_order = config.get("condition_order", [])
        for condition in condition_order:
            if condition == "base":
                continue  # Skip no-assistance (baseline) steps
            images = config.get(condition, [])
            for image in images:
                flat_sequence.append({
                    "condition": condition,
                    "activity": "storytelling",
                    "image": image,
                    "step": step_number
                })
                step_number += 1
        
        return flat_sequence
    
    def _load_participant_file(self, user_number: int) -> Optional[Dict]:
        """
        Load participant sequence configuration from JSON file
        
        Args:
            user_number: Participant number (1-100)
            
        Returns:
            Configuration dict if file exists and is valid, None otherwise
        """
        participant_file = self.participants_dir / f"{user_number}.json"
        
        if not participant_file.exists():
            logger.warning(f"⚠️ Participant file not found: {participant_file}")
            return None
        
        try:
            with open(participant_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract "default" key from participant JSON
            if "default" in data:
                logger.info(f"✅ Loaded participant file: {participant_file}")
                return data["default"]
            else:
                logger.error(f"❌ Participant file missing 'default' key: {participant_file}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in participant file {participant_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error loading participant file {participant_file}: {e}")
            return None
    
    def get_participant_sequence(self, user_number: int) -> Optional[List[Dict]]:
        """
        Get sequence for a specific participant, falling back to default if file doesn't exist
        
        Args:
            user_number: Participant number (1-100)
            
        Returns:
            List of sequence steps, or None if both participant and default fail
        """
        # Try to load participant file
        participant_config = self._load_participant_file(user_number)
        
        if participant_config:
            # Validate structure
            if not self._validate_sequence_config(participant_config):
                logger.warning(f"⚠️ Participant {user_number} config invalid, falling back to default")
                participant_config = None
        
        # Fall back to default if participant file doesn't exist or is invalid
        if not participant_config:
            logger.info(f"📋 Using default sequence for participant {user_number}")
            participant_config = self.sequences.get("default")
        
        if participant_config:
            flat_sequence = self._flatten_sequence(participant_config)
            logger.info(f"📋 Retrieved sequence for participant {user_number} with {len(flat_sequence)} steps")
            return flat_sequence
        
        return None
    
    def _validate_sequence_config(self, config: Dict) -> bool:
        """
        Validate that a sequence configuration has the required structure
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if valid, False otherwise
        """
        required_keys = ['condition_order', 'assistance', 'eye_assistance']
        
        if not all(key in config for key in required_keys):
            logger.error(f"❌ Missing required keys in config: {required_keys}")
            return False
        
        if not isinstance(config['condition_order'], list):
            logger.error("❌ 'condition_order' must be a list")
            return False
        
        for condition in ['assistance', 'eye_assistance']:
            if not isinstance(config[condition], list):
                logger.error(f"❌ '{condition}' must be a list")
                return False
        
        return True
    
    def get_sequence(self, sequence_id: str = "default") -> Optional[List[Dict]]:
        """
        Get a predefined sequence by ID, flattened into step list
        
        Args:
            sequence_id: ID of the sequence to retrieve (default: "default")
                         Can also be a numeric string representing participant number
            
        Returns:
            List of sequence steps, or None if not found
        """
        # Check if sequence_id is a numeric participant number
        try:
            user_number = int(sequence_id)
            if 1 <= user_number <= 100:
                return self.get_participant_sequence(user_number)
        except (ValueError, TypeError):
            pass  # Not a number, continue with normal lookup
        
        # Normal sequence lookup
        config = self.sequences.get(sequence_id)
        if not config:
            logger.warning(f"⚠️ Sequence '{sequence_id}' not found, using default")
            config = self.sequences.get("default")
        
        if config:
            flat_sequence = self._flatten_sequence(config)
            logger.info(f"📋 Retrieved sequence '{sequence_id}' with {len(flat_sequence)} steps")
            return flat_sequence
        
        return None
    
    def list_sequences(self) -> List[str]:
        """
        List all available sequence IDs
        
        Returns:
            List of sequence ID strings
        """
        return list(self.sequences.keys())
    
    def validate_sequence_step(self, step: Dict) -> bool:
        """
        Validate that a sequence step has required fields and valid values (Storytelling only)
        
        Args:
            step: Dictionary representing a sequence step
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['condition', 'activity', 'image', 'step']
        valid_conditions = ['assistance', 'eye_assistance']
        valid_activities = ['storytelling']  # Only storytelling now
        
        # Check required fields
        if not all(field in step for field in required_fields):
            logger.error(f"❌ Missing required fields in step: {step}")
            return False
        
        # Validate condition
        if step['condition'] not in valid_conditions:
            logger.error(f"❌ Invalid condition: {step['condition']}")
            return False
        
        # Validate activity (must be storytelling)
        if step['activity'] not in valid_activities:
            logger.error(f"❌ Invalid activity: {step['activity']} (must be 'storytelling')")
            return False
        
        # Validate step number
        if not isinstance(step['step'], int) or step['step'] < 1:
            logger.error(f"❌ Invalid step number: {step['step']}")
            return False
        
        return True


# Global instance
_sequence_config_service: Optional[SequenceConfigService] = None


def get_sequence_config_service() -> SequenceConfigService:
    """Get the global SequenceConfigService instance"""
    global _sequence_config_service
    if _sequence_config_service is None:
        _sequence_config_service = SequenceConfigService()
    return _sequence_config_service

