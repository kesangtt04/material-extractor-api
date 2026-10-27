# Material Extractor

**AI-powered material extraction** từ File (Excel, PDF, CSV, Word) và Text Chat tiếng Việt. 
Hệ thống sử dụng kết hợp Machine Learning truyền thống và Deep Learning để bóc tách dữ liệu vật tư tự động.

---

## 🚀 Quick Start

### 1. Cài đặt môi trường
Dự án yêu cầu Python 3.11+. Nên sử dụng virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu  # Bản CPU
python -m pip install -e ".[dev]"
```

Các dependency runtime và development được khai báo trong `pyproject.toml`. Trên Linux, cần cài thư viện hệ thống `libmagic` để `python-magic` nhận diện định dạng file.

Các checkpoint đã huấn luyện và dữ liệu runtime (`text_models/`, `file_models/`, `data/`) không được nhúng vào wheel; khi triển khai từ package cần cung cấp các thư mục asset này theo cấu trúc dự án.

### 2. Chạy Web UI (FastAPI)
```bash
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```
Truy cập trình duyệt tại: **http://127.0.0.1:8000**

---

## 🌟 Kiến Trúc & Features

Dự án bao gồm **2 Pipeline hoàn toàn độc lập** phục vụ 2 luồng input khác nhau:

### 1. FILE Pipeline (Trích xuất từ Bảng tính / Tài liệu)
- **Input:** Excel (`.xlsx`, `.xls`), CSV, Word (`.docx`, `.doc`), PDF.
- File Excel `.xls` is read with `xlrd`. Reading legacy Word `.doc` files requires LibreOffice installed on the server and `soffice` available on `PATH`; `.docx` does not need this external tool.
- **Xử lý:** Tự động tìm kiếm cấu trúc bảng, nhận diện các cột vật tư qua cơ chế Waterfall (3 tầng).
- **Mô hình (Tier 2):** Sử dụng **Random Forest** (Scikit-learn) để phân loại cột dựa trên đặc trưng văn bản, hỗ trợ cả bảng không có header (NO-HEADER).
- **Đầu ra:** Danh sách vật tư chuẩn hóa (Mã, Tên, Đơn vị, Số lượng).

### 2. TEXT Pipeline (Trích xuất từ Câu chat tự nhiên)
- **Input:** Câu chat tiếng Việt phi cấu trúc (VD: *"Lấy cho anh 20 cái bulong M10 mã BL10 và 5 cuộn băng keo"*).
- **Xử lý:** Nhận dạng thực thể có tên (NER - Named Entity Recognition) với hệ nhãn `NAME`, `QTY`, `UNIT`, `CODE`.
- **Mô hình:** Deep Learning **BiLSTM-CRF** (PyTorch) với character-level embeddings giúp xử lý tốt lỗi chính tả tiếng Việt.
- **Đầu ra:** Các object vật tư được trích xuất và gom nhóm thông minh.

---

## 📂 Cấu Trúc Dự Án

```text
material-extractor/
├── app.py                      # Main FastAPI server (Giao diện & API)
├── data/
│   ├── file/                   # Dữ liệu mẫu test file pipeline
│   └── text/                   # Dữ liệu training cho text model (corpus, splits, cache)
├── file_pipeline/              # 📌 HỆ THỐNG XỬ LÝ FILE
│   ├── extractor.py            # Entry point bóc tách file
│   ├── document_readers.py     # Đọc grid từ Excel, PDF, Word
│   ├── header_detection.py     # Heuristic tầng 1 (Header aliases)
│   ├── ml_validation.py        # Phân loại bằng ML (Tầng 2)
│   └── ...
├── text_pipeline/              # 📌 HỆ THỐNG XỬ LÝ TEXT
│   ├── service.py              # Entry point bóc tách text
│   ├── preprocessor.py         # Tiền xử lý NLP
│   ├── bilstm_crf/             # Kiến trúc model PyTorch (Model, Parser, Trainer, Vocab)
│   └── scripts/                # Scripts tiện ích & training cho Text
├── file_models/                # Nơi lưu model .joblib (Random Forest)
├── text_models/                # Nơi lưu model .pt & .pkl (BiLSTM-CRF)
├── templates/                  # HTML templates cho FastAPI (index.html)
├── tests/                      # Unit tests (pytest)
├── scripts/                    # Các kịch bản phụ trợ khác
└── training/                   # Scripts training cho File Pipeline (train_file.py)
```

---

## ⚙️ Chi Tiết Luồng Xử Lý (Processing Flow)

### 1. Luồng Xử Lý Text (Text Pipeline)
Quy trình từ lúc nhận câu chat đến khi ra JSON vật tư:
1. **Tiền xử lý (Pre-processing):** Chuẩn hóa khoảng trắng, ngắt câu đa sản phẩm (dấu phẩy, liên từ "và", "cùng với").
2. **Tokenization:** Tách từ (word-level) và tách ký tự (character-level) để bắt lỗi chính tả tiếng Việt.
3. **Mô hình AI (BiLSTM-CRF):** Đưa qua PyTorch Model. BiLSTM rút trích ngữ cảnh hai chiều, CRF (Conditional Random Field) tối ưu hóa chuỗi nhãn BIO liên tiếp. *Đặc biệt, model đã được huấn luyện để tự động nhận diện ranh giới vật tư (chuyển tiếp `B-NAME -> B-QTY`) cho câu không chứa dấu phẩy (VD: "5 cái búa hai bịch phe gài").*
4. **Hậu xử lý (Post-processing) với Auto-split State Machine:** Gom các từ có nhãn tương ứng (`B-NAME`, `I-NAME`, `B-QTY`, `B-UNIT`). Sử dụng cỗ máy trạng thái (State Machine) thông minh để tự động phân tách (split) các cụm vật tư liền kề nhau khi phát hiện nhãn trùng lặp trong cùng một chuỗi, tránh hoàn toàn việc sử dụng luật if/else cứng nhắc. Ghép số lượng (`QTY`) với đơn vị (`UNIT`) và mã (`CODE`).

### 2. Luồng Xử Lý File (File Pipeline)
1. **Data Ingestion:** Đọc file PDF, Word, Excel, CSV chuyển thành cấu trúc lưới (Grid 2D).
2. **Quy trình bóc tách 3 Tầng (Waterfall):** Đảm bảo độ chính xác cao và linh hoạt với file rác:
   - **Tier 1 (Header Heuristics):** So khớp trực tiếp dòng tiêu đề với bộ từ điển từ khóa (Aliases) đã được ánh xạ chuẩn (Ví dụ: "Tên vật tư", "Description", "Part #").
   - **Tier 1b (SKU Fallback):** Nếu không có Header, tìm kiếm dòng chứa các mã cấu trúc giống SKU, lấy đó làm điểm neo định vị.
   - **Tier 2 (ML Classification):** Nếu các luật trên thất bại, mô hình Random Forest sẽ đo lường đặc trưng của từng cột (độ dài, tỷ lệ số, ký tự đặc biệt) để dự đoán chức năng cột đó.

---

## 🧠 Hướng Dẫn & Luồng Training (Luồng Độc Lập)

> **QUAN TRỌNG:** Hai luồng model (Text và File) sử dụng dữ liệu, thuật toán và script hoàn toàn khác nhau.

### 🔹 Luồng 1: Train TEXT Model (BiLSTM-CRF)
- **Cơ chế train:** Load dữ liệu JSONL, tokenize từ vựng, lưu tensor cache. Huấn luyện qua các epoch với Optimizer (OneCycleLR) và Gradient Clipping. Đánh giá loss trên tập Validation và lưu mô hình tốt nhất.
- **Framework:** PyTorch
- **Script:** `text_pipeline/scripts/train_fast.py`
- **Output:** File `.pt` (trọng số) và `.pkl` (từ vựng) vào thư mục `text_models/`

**Các lệnh phổ biến:**
```bash
# Train nhanh để test logic (vài phút)
python text_pipeline/scripts/train_fast.py --profile fast

# Train chuẩn (khuyên dùng - 30-60 phút)
python text_pipeline/scripts/train_fast.py --profile normal

# Cập nhật lại replay splits nếu data gốc thay đổi
python text_pipeline/scripts/prepare_v32_full_text_data.py
```

### 🔹 Luồng 2: Train FILE Model (Random Forest)
- **Cơ chế train:** Sinh dữ liệu tổng hợp (Synthetic Data Generator) mô phỏng lỗi bảng ngang/dọc, missing cell, no-header (5,000 blocks mới). Trích xuất đặc trưng cột (Feature Engineering) và huấn luyện qua Random Forest.
- **Framework:** Scikit-learn
- **Script:** `training/train_file.py` (hoặc các version cũ hơn trong `scripts/`)
- **Output:** File `.joblib` và `.json` vào thư mục `file_models/` (hoặc `models/`)
- **Data:** Tự động generate (synthetic data) mô phỏng các bảng lỗi, mất header, bảng dọc/ngang.

**Lệnh train:**
```bash
python training/train_file.py
```

---

## 🧪 Testing

Chạy toàn bộ Unit Tests bằng `pytest` (cài tùy chọn development bằng `python -m pip install -e ".[dev]"`):

```bash
# Chạy toàn bộ test
pytest tests/

# Chỉ chạy test file pipeline
pytest tests/file/

# Chỉ chạy test text pipeline
pytest tests/text/
```

### Chạy test nhanh qua Python CLI
**Test Text Pipeline:**
```python
from text_pipeline.service import TextParserService
service = TextParserService()

# Test 1 vật tư
print(service.parse_query({"query": "20 cái bulong lục giác M10"}))

# Test nhiều vật tư không có dấu phẩy ngăn cách
print(service.parse_query({"query": "5 cái búa hai bịch phe gài"}))
```

**Test File Pipeline:**
```python
from file_pipeline.extractor import extract_material_data_detailed
results, details = extract_material_data_detailed("data/file/test/testtutao.xlsx")
print(results)
```

---

## 🛠 Tech Stack
- **Backend/API:** FastAPI, Uvicorn, Jinja2
- **Text NLP Model:** PyTorch, TorchCRF
- **File ML Model:** Scikit-learn, Joblib, Numpy, Pandas
- **Document Parsing:** PDFPlumber, openpyxl, python-docx
- **File Validation:** python-magic
