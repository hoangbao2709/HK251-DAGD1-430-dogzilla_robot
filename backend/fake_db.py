import pandas as pd
import sqlite3

# 1. Đọc dữ liệu từ file CSV đã được chỉnh sửa
try:
    df = pd.read_csv('control_patrolhistory.csv')
    print(f"Đã đọc thành công {len(df)} dòng từ file CSV.")
except Exception as e:
    print(f"Lỗi khi đọc file CSV: {e}")
    exit()

# 2. Kết nối tới database SQLite
conn = sqlite3.connect('app.sqlite3')
cursor = conn.cursor()

# 3. Chuẩn bị dữ liệu để UPDATE
# Chúng ta sẽ dựa vào cột 'id' để cập nhật chính xác các cột còn lại
updates = []
for index, row in df.iterrows():
    # Gom dữ liệu thành một tuple theo đúng thứ tự câu truy vấn bên dưới
    updates.append((
        row['mission_id'], 
        row['route_name'], 
        row['status'], 
        row['started_at'], 
        row['finished_at'], 
        row['payload'], 
        row['created_at'], 
        row['robot_id'], 
        row['total_distance_m'], 
        row['cpu_samples'], 
        row['battery_samples'], 
        row['temperature_samples'], 
        row['ram_samples'], 
        row['id'] # id nằm cuối cùng cho mệnh đề WHERE
    ))

# Câu lệnh SQL để cập nhật toàn bộ các trường của một dòng dựa trên ID
update_query = """
UPDATE control_patrolhistory 
SET mission_id = ?, 
    route_name = ?, 
    status = ?, 
    started_at = ?, 
    finished_at = ?, 
    payload = ?, 
    created_at = ?, 
    robot_id = ?, 
    total_distance_m = ?, 
    cpu_samples = ?, 
    battery_samples = ?, 
    temperature_samples = ?, 
    ram_samples = ?
WHERE id = ?
"""

# 4. Thực thi và lưu thay đổi
try:
    cursor.executemany(update_query, updates)
    conn.commit()
    print("Đã cập nhật thành công toàn bộ dữ liệu từ CSV vào bảng control_patrolhistory!")
except Exception as e:
    conn.rollback()
    print(f"Lỗi khi cập nhật database: {e}")
finally:
    conn.close()