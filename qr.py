"""
Chương trình đọc mã QR từ hình ảnh hoặc camera
"""

import cv2
from pyzbar.pyzbar import decode
import sys
from pathlib import Path


def decode_qr_from_image(image_path):
    """
    Đọc mã QR từ file hình ảnh
    
    Args:
        image_path: đường dẫn đến file hình ảnh
    
    Returns:
        danh sách dữ liệu được giải mã
    """
    try:
        # Đọc hình ảnh
        image = cv2.imread(image_path)
        
        if image is None:
            print(f"Không thể đọc file: {image_path}")
            return []
        
        # Giải mã mã QR
        decoded_objects = decode(image)
        
        if not decoded_objects:
            print("Không tìm thấy mã QR trong hình ảnh")
            return []
        
        results = []
        for i, obj in enumerate(decoded_objects, 1):
            data = obj.data.decode('utf-8')
            print(f"\nMã QR #{i}:")
            print(f"  Dữ liệu: {data}")
            print(f"  Loại: {obj.type}")
            results.append(data)
        
        return results
    
    except Exception as e:
        print(f"Lỗi khi xử lý hình ảnh: {e}")
        return []


def decode_qr_from_webcam(delay=500):
    """
    Đọc mã QR từ camera webcam
    
    Args:
        delay: độ trễ giữa các frame (ms)
    """
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Không thể mở camera")
        return
    
    print("Bắt đầu đọc mã QR từ camera...")
    print("Nhấn 'q' để thoát")
    
    found_codes = set()
    
    try:
        while True:
            ret, frame = cap.read()
            
            if not ret:
                print("Không thể đọc frame từ camera")
                break
            
            # Giải mã mã QR
            decoded_objects = decode(frame)
            
            # Vẽ hình chữ nhật quanh mã QR tìm thấy
            for obj in decoded_objects:
                # Lấy tọa độ
                x, y, w, h = obj.rect.left, obj.rect.top, obj.rect.width, obj.rect.height
                
                # Vẽ hình chữ nhật xanh lá cây
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                # Giải mã dữ liệu
                data = obj.data.decode('utf-8')
                
                # Hiển thị dữ liệu lên frame
                cv2.putText(frame, data, (x, y - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                # In thông tin nếu là mã mới
                if data not in found_codes:
                    found_codes.add(data)
                    print(f"\n✓ Tìm thấy mã QR mới:")
                    print(f"  Dữ liệu: {data}")
                    print(f"  Loại: {obj.type}")
            
            # Hiển thị frame
            cv2.imshow("QR Code Reader - Nhấn 'q' để thoát", frame)
            
            # Thoát với phím 'q'
            if cv2.waitKey(delay) & 0xFF == ord('q'):
                break
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("\nKết thúc chương trình")


def main():
    """Hàm chính"""
    print("=" * 50)
    print("CHƯƠNG TRÌNH ĐỌC MÃ QR")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        # Đọc QR từ file hình ảnh
        image_path = sys.argv[1]
        
        if Path(image_path).exists():
            print(f"\nĐang xử lý file: {image_path}")
            decode_qr_from_image(image_path)
        else:
            print(f"File không tồn tại: {image_path}")
    else:
        # Đọc QR từ camera
        print("\nChế độ: Đọc từ camera webcam")
        decode_qr_from_webcam()


if __name__ == "__main__":
    main()
