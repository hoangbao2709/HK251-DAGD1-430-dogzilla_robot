# Py-Xiaozhi Bridge

Muc tieu:
- giu nguyen backend Django hien tai
- de `py-xiaozhi` goi lenh robot thong qua MCP tool rieng
- khong phu thuoc vao `xiaozhi.me`

## Kien truc

`py-xiaozhi` -> `py_xiaozhi_bridge_server.py` -> `POST /control/api/xiaozhi/command/` -> `control.services.mcp_voice` -> `robot_mcp_server.py`

## Bien moi truong backend

Dat trong moi truong chay Django:

```env
XIAOZHI_BRIDGE_TOKEN=bridge-secret
XIAOZHI_DEFAULT_ROBOT_ID=robot-a
XIAOZHI_DEFAULT_ROBOT_ADDR=http://192.168.1.50:9000
```

`XIAOZHI_DEFAULT_ROBOT_ADDR` chi la gia tri fallback cuoi cung.
Neu request gui len `robot_addr` hoac `addr`, bridge se uu tien dung gia tri do.
Neu request khong gui dia chi, bridge se thu doc `Robot.addr` da luu trong DB.

## Endpoint moi

- `GET /control/api/xiaozhi/health/`
- `POST /control/api/xiaozhi/command/`

Header:

```http
Authorization: Bearer bridge-secret
```

Payload toi thieu:

```json
{
  "text": "bat tay"
}
```

Payload day du:

```json
{
  "text": "di toi diem A",
  "robot_id": "robot-a",
  "robot_addr": "http://192.168.1.50:9000",
  "dry_run": false
}
```

Bridge cung chap nhan truong `addr` va `robot_ip`.

## MCP adapter cho py-xiaozhi

File adapter:

- [py_xiaozhi_bridge_server.py](/e:/HK251-DAGD1-430-dogzilla_robot/backend/mcp-calculator/py_xiaozhi_bridge_server.py)

Bien moi truong khi chay adapter:

```env
DOGZILLA_BACKEND_BASE_URL=http://127.0.0.1:8000
XIAOZHI_BRIDGE_TOKEN=bridge-secret
XIAOZHI_DEFAULT_ROBOT_ID=robot-a
XIAOZHI_DEFAULT_ROBOT_ADDR=http://192.168.1.50:9000
XIAOZHI_BRIDGE_TIMEOUT=20
```

Tool expose ra cho `py-xiaozhi`:

- `bridge_health`
- `send_robot_text_command`

## Cach noi voi py-xiaozhi

Trong cau hinh MCP cua `py-xiaozhi`, dang ky mot stdio server:

```json
{
  "mcpServers": {
    "dogzilla-backend-bridge": {
      "type": "stdio",
      "command": "python",
      "args": [
        "E:/HK251-DAGD1-430-dogzilla_robot/backend/mcp-calculator/py_xiaozhi_bridge_server.py"
      ],
      "env": {
        "DOGZILLA_BACKEND_BASE_URL": "http://127.0.0.1:8000",
        "XIAOZHI_BRIDGE_TOKEN": "bridge-secret",
        "XIAOZHI_DEFAULT_ROBOT_ID": "robot-a",
        "XIAOZHI_DEFAULT_ROBOT_ADDR": "http://192.168.1.50:9000"
      }
    }
  }
}
```

Sau do trong `py-xiaozhi`, cho phep LLM goi tool `send_robot_text_command`.

## Kiem tra nhanh

Test HTTP bridge:

```bash
curl -X POST http://127.0.0.1:8000/control/api/xiaozhi/command/ ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer bridge-secret" ^
  -d "{\"text\":\"bat tay\"}"
```

Test MCP adapter:

```bash
python backend/mcp-calculator/py_xiaozhi_bridge_server.py
```
