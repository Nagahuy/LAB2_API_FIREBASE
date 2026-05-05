# LAB 2: API & FIREBASE STUDIO

**Sinh viên thực hiện:** 24120064 - Trương Đình Nhật Huy

## 1. Mô Tả Dự Án

Study Chatbot là ứng dụng chatbot học tập chạy trên web, cho phép người dùng đăng ký, đăng nhập, đặt câu hỏi học tập và xem lại lịch sử từng đoạn chat. Hệ thống sử dụng FastAPI cho backend, HTML/CSS/JavaScript thuần cho frontend, Firebase Authentication để xác thực người dùng và Firestore để lưu dữ liệu hội thoại.

Feature chính của ứng dụng là chatbot học tập chạy bằng model local thông qua `llama.cpp` server. Backend gọi model qua API tương thích OpenAI tại `http://127.0.0.1:8080/v1/chat/completions`.

**Tính năng chính**

- **Đăng ký, đăng nhập:** Hỗ trợ Email/Password và Google Login thông qua Firebase Authentication.
- **Xác thực API:** Các API cá nhân yêu cầu Firebase ID token trong header `Authorization`.
- **Chatbot học tập:** Người dùng đặt câu hỏi toán học, lập trình hoặc kiến thức học tập; backend gọi model local để trả lời.
- **Quản lý lịch sử chat:** Firestore lưu từng session chat theo user, có thể chọn lại đoạn chat cũ và tiếp tục trò chuyện.
- **Giao diện web:** Frontend HTML/CSS/JS đơn giản, tone cam, có login/logout, sidebar lịch sử, khung chat và thông báo lỗi.

## 2. Hướng Dẫn Cài Đặt Environment

**Yêu cầu hệ thống**

- Python 3.10 trở lên
- Conda
- Firebase project đã bật Authentication và Firestore
- `llama.cpp` có `llama-server`

**Clone repository**

```bash
git clone https://github.com/Nagahuy/LAB2_API_FIREBASE.git
cd LAB2_API_FIREBASE
```

**Tạo và kích hoạt conda environment**

```bash
conda create -n labFirebase python=3.10 -y
conda activate labFirebase
```

**Cài đặt thư viện Python**

```bash
pip install -r requirements.txt
```

**Tạo file môi trường**

```bash
cp .env.example .env
```

Điền thông tin Firebase, Google OAuth và model vào `.env`. Các giá trị quan trọng:

```env
FIREBASE_WEB_API_KEY=your_firebase_web_api_key
FIREBASE_PROJECT_ID=your_firebase_project_id
FIREBASE_SERVICE_ACCOUNT_FILE=./firebase-service-account.json

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
FRONTEND_URL=http://127.0.0.1:8501
BACKEND_URL=http://127.0.0.1:8000

LLAMA_BASE_URL=http://127.0.0.1:8080
LLAMA_MODEL=study-bot
HF_TOKEN=
```

Trong Google Cloud Console, OAuth Client phải có redirect URI:

```text
http://127.0.0.1:8000/auth/google/callback
```

Service account JSON tải từ Firebase Console và đặt tại:

```text
firebase-service-account.json
```

## 3. Hướng Dẫn Chạy Model Local Bằng llama.cpp

`llama-server` không nằm trong `requirements.txt`, cần cài hoặc build riêng từ `llama.cpp`.

```bash
llama-server \
  --hf-repo Qwen/Qwen2.5-3B-Instruct-GGUF \
  --hf-file qwen2.5-3b-instruct-q4_k_m.gguf \
  -c 2048 \
  --host 127.0.0.1 \
  --port 8080 \
  -a study-bot
```

## 4. Hướng Dẫn Chạy Backend

Backend được xây dựng bằng FastAPI.

```bash
conda activate labFirebase
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## 5. Hướng Dẫn Chạy Frontend

Frontend được xây dựng bằng HTML, CSS và JavaScript thuần.

```bash
cd frontend
python -m http.server 8501 --bind 127.0.0.1
```

Mở ứng dụng tại:

```text
http://127.0.0.1:8501
```

## 6. Đường Dẫn Đến Video Demo

Video demo giới thiệu luồng đăng ký, đăng nhập, xác thực Firebase, gửi câu hỏi cho chatbot, xem lại lịch sử chat và kiểm tra dữ liệu được lưu trong Firestore.

**Link Video:** `<link demo>`

## 7. Danh Sách API Endpoints

- `GET /`: Kiểm tra API chính có hoạt động không.
- `GET /health`: Kiểm tra trạng thái backend.
- `POST /auth/signup`: Đăng ký tài khoản bằng Email/Password qua Firebase Authentication.
- `POST /auth/login`: Đăng nhập bằng Email/Password và nhận Firebase ID token.
- `GET /auth/google/start`: Bắt đầu luồng đăng nhập Google OAuth.
- `GET /auth/google/callback`: Nhận callback từ Google, đổi sang Firebase ID token và redirect về frontend.
- `GET /auth/me`: Lấy thông tin user hiện tại, yêu cầu Bearer token.
- `GET /chat/sessions`: Lấy danh sách các đoạn chat của user hiện tại, yêu cầu Bearer token.
- `POST /chat/sessions`: Tạo một đoạn chat mới, yêu cầu Bearer token.
- `GET /chat/messages`: Lấy tin nhắn trong một đoạn chat theo `session_id`, yêu cầu Bearer token.
- `POST /chat`: Gửi câu hỏi tới chatbot, gọi llama.cpp, lưu user message và assistant reply vào Firestore.
