"""
Image Cropping Service for Manual Assistance
Handles AOI extraction from full images
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

class ImageCroppingService:
    """Service for cropping AOI regions from full images"""
    
    def __init__(self):
        self.images_dir = Path("../pictures")
        
    def crop_aoi_from_image(
        self, 
        image_filename: str, 
        activity: str, 
        bbox: list
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Crop AOI region from full image
        
        Args:
            image_filename: e.g., "1.jpg"
            activity: "storytelling" only
            bbox: [x1, y1, x2, y2] pixel coordinates
            
        Returns:
            Tuple of (cropped_image_base64, full_image_base64) or (None, None) if error
        """
        try:
            if Image is None:
                logger.error("❌ PIL not available for image cropping")
                return None, None
            
            # Construct image path
            image_path = self.images_dir / activity / image_filename
            
            if not image_path.exists():
                logger.error(f"❌ Image not found: {image_path}")
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
                    logger.error(f"❌ Invalid bounding box: {bbox}")
                    return None, None
                
                # Ensure coordinates are within image bounds
                img_width, img_height = full_image.size
                x1 = max(0, min(x1, img_width))
                x2 = max(0, min(x2, img_width))
                y1 = max(0, min(y1, img_height))
                y2 = max(0, min(y2, img_height))
                
                # Crop the AOI region
                cropped_image = full_image.crop((x1, y1, x2, y2))
                
                logger.info(f"✂️ Cropped AOI: {bbox} from {image_filename} ({img_width}x{img_height})")
                logger.info(f"📏 Cropped size: {cropped_image.size}")
                
                # Convert both images to base64 for API transmission
                full_image_b64 = self._image_to_base64(full_image)
                cropped_image_b64 = self._image_to_base64(cropped_image)
                
                return cropped_image_b64, full_image_b64
                
        except Exception as e:
            logger.error(f"❌ Error cropping image: {e}")
            return None, None
    
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
            
            # Save image to bytes buffer
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=90)
            buffer.seek(0)
            
            # Encode to base64
            image_bytes = buffer.getvalue()
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            
            return base64_string
            
        except Exception as e:
            logger.error(f"❌ Error converting image to base64: {e}")
            return ""
    
    def crop_two_aois_from_image(
        self, 
        image_filename: str, 
        activity: str, 
        aoi1_bbox: list,  # PRIMARY (assisted)
        aoi2_bbox: list   # SECONDARY (connected)
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Crop two AOIs and full page, return three base64 images
        Returns: (aoi1_b64, aoi2_b64, full_b64)
        """
        try:
            image_path = self.images_dir / activity / image_filename
            
            if not image_path.exists():
                logger.error(f"❌ Image not found: {image_path}")
                return None, None, None
                
            with Image.open(image_path) as image:
                # Crop first AOI (PRIMARY - assisted)
                aoi1_crop = image.crop(aoi1_bbox)
                aoi1_b64 = self._image_to_base64(aoi1_crop)
                
                # Crop second AOI (SECONDARY - connected)
                aoi2_crop = image.crop(aoi2_bbox)
                aoi2_b64 = self._image_to_base64(aoi2_crop)
                
                # Get full page as base64
                full_b64 = self._image_to_base64(image)
                
                logger.info(f"✅ Cropped two AOIs from {image_filename}: AOI1 {aoi1_bbox}, AOI2 {aoi2_bbox}")
                
                return aoi1_b64, aoi2_b64, full_b64
                
        except Exception as e:
            logger.error(f"❌ Error cropping two AOIs from {image_filename}: {e}")
            return None, None, None

    def get_image_dimensions(self, image_filename: str, activity: str) -> Optional[Tuple[int, int]]:
        """Get image dimensions for coordinate validation"""
        try:
            image_path = self.images_dir / activity / image_filename
            
            if not image_path.exists():
                return None
                
            with Image.open(image_path) as image:
                return image.size
                
        except Exception as e:
            logger.error(f"❌ Error getting image dimensions: {e}")
            return None

# Global instance
_image_cropping_service: Optional[ImageCroppingService] = None

def get_image_cropping_service() -> ImageCroppingService:
    """Get the global image cropping service instance"""
    global _image_cropping_service
    if _image_cropping_service is None:
        _image_cropping_service = ImageCroppingService()
    return _image_cropping_service
