"""
Image Cropping Service for Eye-Tracking Assistance
Separate from manual assistance - handles AOI extraction for gaze-triggered guidance
"""
import logging
import base64
import io
from typing import Tuple, Optional
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("❌ PIL not installed. Install with: pip install Pillow")
    Image = None

logger = logging.getLogger(__name__)

class EyeTrackingImageCroppingService:
    """Service for cropping AOI regions for eye-tracking guidance"""
    
    def __init__(self):
        self.images_dir = Path("../pictures")
        
    def crop_aoi_from_image(
        self, 
        image_filename: str, 
        activity: str, 
        bbox: list
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Crop AOI region from full image for eye-tracking analysis
        
        Args:
            image_filename: e.g., "1.jpg" or "1.png"
            activity: "storytelling" only
            bbox: [x1, y1, x2, y2] pixel coordinates
            
        Returns:
            Tuple of (cropped_image_base64, full_image_base64) or (None, None) if error
        """
        try:
            if Image is None:
                logger.error("❌ PIL not available for eye-tracking image cropping")
                return None, None
            
            # Construct image path
            image_path = self.images_dir / activity / image_filename
            
            if not image_path.exists():
                logger.error(f"❌ Eye-tracking image not found: {image_path}")
                return None, None
            
            # Load the full image
            with Image.open(image_path) as full_image:
                # Convert to RGB if needed
                if full_image.mode != 'RGB':
                    full_image = full_image.convert('RGB')
                
                # Extract bounding box coordinates
                x1, y1, x2, y2 = bbox
                
                # Validate coordinates
                if x1 >= x2 or y1 >= y2:
                    logger.error(f"❌ Invalid bounding box for eye-tracking: {bbox}")
                    return None, None
                
                # Ensure coordinates are within image bounds
                img_width, img_height = full_image.size
                x1 = max(0, min(x1, img_width))
                x2 = max(0, min(x2, img_width))
                y1 = max(0, min(y1, img_height))
                y2 = max(0, min(y2, img_height))
                
                # Crop the AOI region
                cropped_image = full_image.crop((x1, y1, x2, y2))
                
                logger.info(f"✂️ Eye-tracking: Cropped AOI from {image_filename} ({img_width}x{img_height})")
                
                # Convert both images to base64
                full_image_b64 = self._image_to_base64(full_image)
                cropped_image_b64 = self._image_to_base64(cropped_image)
                
                return cropped_image_b64, full_image_b64
                
        except Exception as e:
            logger.error(f"❌ Error in eye-tracking image cropping: {e}")
            return None, None
    
    def crop_two_aois_from_image(
        self,
        image_filename: str,
        activity: str,
        aoi1_bbox: list,
        aoi2_bbox: list
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Crop two AOIs and full page, return three base64 images
        Returns: (aoi1_b64, aoi2_b64, full_b64)
        """
        try:
            if Image is None:
                logger.error("❌ PIL not available for eye-tracking image cropping")
                return None, None, None
            
            image_path = self.images_dir / activity / image_filename
            
            if not image_path.exists():
                logger.error(f"❌ Eye-tracking image not found: {image_path}")
                return None, None, None
                
            with Image.open(image_path) as image:
                # Crop first AOI (PRIMARY - gazed)
                aoi1_crop = image.crop(aoi1_bbox)
                aoi1_b64 = self._image_to_base64(aoi1_crop)
                
                # Crop second AOI (SECONDARY - closest unassisted)
                aoi2_crop = image.crop(aoi2_bbox)
                aoi2_b64 = self._image_to_base64(aoi2_crop)
                
                # Get full page as base64
                full_b64 = self._image_to_base64(image)
                
                logger.info(f"✅ Eye-tracking: Cropped two AOIs from {image_filename}")
                
                return aoi1_b64, aoi2_b64, full_b64
                
        except Exception as e:
            logger.error(f"❌ Error cropping two AOIs: {e}")
            return None, None, None

    def _image_to_base64(self, image) -> str:
        """Convert PIL Image to base64 string"""
        try:
            # Convert RGBA to RGB if necessary (remove alpha channel)
            if image.mode == 'RGBA':
                # Create a white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
                image = background
            elif image.mode not in ('RGB', 'L'):
                # Convert other modes to RGB
                image = image.convert('RGB')
            
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=90)
            buffer.seek(0)
            
            image_bytes = buffer.getvalue()
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            
            return base64_string
            
        except Exception as e:
            logger.error(f"❌ Error converting image to base64: {e}")
            return ""

# Global instance
_eye_tracking_cropping_service: Optional[EyeTrackingImageCroppingService] = None

def get_eye_tracking_cropping_service() -> EyeTrackingImageCroppingService:
    """Get the global eye-tracking cropping service instance"""
    global _eye_tracking_cropping_service
    if _eye_tracking_cropping_service is None:
        _eye_tracking_cropping_service = EyeTrackingImageCroppingService()
    return _eye_tracking_cropping_service
