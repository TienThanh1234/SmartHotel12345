from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import os
import re
from datetime import datetime

app = Flask(__name__)

# === FILE PATHS ===
HOTELS_CSV = "hotels.csv"
REVIEWS_CSV = "reviews.csv"
BOOKINGS_CSV = "bookings.csv"

# === ĐẢM BẢO FILE TỒN TẠI ===
if not os.path.exists(HOTELS_CSV):
    raise FileNotFoundError("❌ Không tìm thấy hotels.csv — hãy thêm file này trước!")

if not os.path.exists(REVIEWS_CSV):
    pd.DataFrame(columns=["hotel_name", "user", "rating", "comment"]).to_csv(
        REVIEWS_CSV, index=False, encoding="utf-8-sig"
    )

if not os.path.exists(BOOKINGS_CSV):
    pd.DataFrame(columns=[
        "hotel_name", "room_type", "price", "user_name", "phone", "email",
        "num_adults", "num_children", "checkin_date", "nights", "special_requests", "booking_time"
    ]).to_csv(BOOKINGS_CSV, index=False, encoding="utf-8-sig")


# === HÀM ĐỌC CSV AN TOÀN VÀ CHUẨN HÓA DỮ LIỆU SỐ ===
def read_csv_safe(file_path):
    encodings = ["utf-8-sig", "utf-8", "cp1252"]
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc, dtype=str)
            df.columns = df.columns.str.strip()  # loại bỏ khoảng trắng ở tên cột

            # Tự động convert các cột số nếu tồn tại
            numeric_cols = ['price', 'stars', 'rating', 'num_adults', 'num_children', 'nights']
            for col in numeric_cols:
                if col in df.columns:
                    # loại bỏ dấu ',' rồi convert sang float
                    df[col] = df[col].str.replace(',', '').astype(float)

            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý file {file_path}: {e}")
            raise
    raise UnicodeDecodeError(f"Không đọc được file {file_path} với UTF-8 hoặc cp1252!")


# === LOAD DỮ LIỆU ===
hotels = read_csv_safe(HOTELS_CSV)
reviews_df = read_csv_safe(REVIEWS_CSV)

if 'name' not in hotels.columns:
    if 'Name' in hotels.columns:
        hotels = hotels.rename(columns={'Name': 'name'})
    else:
        raise KeyError("❌ hotels.csv không có cột 'name'. Vui lòng kiểm tra header CSV!")

if 'hotel_name' not in reviews_df.columns:
    raise KeyError("❌ reviews.csv không có cột 'hotel_name'.")


# === HÀM PHỤ TRỢ ===
def yes_no_icon(val):
    return "✅" if str(val).lower() in ("true", "1", "yes") else "❌"


def map_hotel_row(row):
    h = dict(row)
    h["image"] = h.get("image_url", h.get("image", ""))
    html_desc = h.get("review") or h.get("description") or ""
    h["full_desc"] = html_desc  # để dùng chi tiết
    # tạo short_desc cho danh sách
    import re
    clean = re.sub(r'<[^>]*>', '', html_desc)  # loại bỏ tag
    h["short_desc"] = clean[:150] + ("..." if len(clean) > 150 else "")
    
    h["gym"] = h.get("gym", False)
    h["spa"] = h.get("spa", False)
    h["sea_view"] = h.get("sea") if "sea" in h else h.get("sea_view", False)
    return h


# === TRANG CHỦ ===
@app.route('/')
def home():
    cities = sorted(hotels['city'].dropna().unique())
    return render_template('index.html', cities=cities), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === TRANG GỢI Ý ===
@app.route('/recommend', methods=['POST', 'GET'])
def recommend():
    filtered = hotels.copy()

    if request.method == 'POST':
        city = request.form.get('location', '').lower()
        budget = request.form.get('budget', '')
        stars = request.form.get('stars', '')
    else:
        city = request.args.get('location', '').lower()
        budget = request.args.get('budget', '')
        stars = request.args.get('stars', '')

    if city:
        filtered = filtered[filtered['city'].str.lower() == city]

    if budget:
        try:
            budget = float(budget)
            filtered = filtered[filtered['price'] <= budget]
        except ValueError:
            pass

    if stars:
        try:
            stars = int(stars)
            filtered = filtered[filtered['stars'] >= stars]
        except ValueError:
            pass

    for col in ['buffet', 'pool', 'sea', 'view']:
        if request.args.get(col):
            filtered = filtered[filtered[col] == True]

    sort = request.args.get('sort', '')
    if sort == 'asc':
        filtered = filtered.sort_values(by='price')
    elif sort == 'desc':
        filtered = filtered.sort_values(by='price', ascending=False)

    results = [map_hotel_row(r) for r in filtered.to_dict(orient='records')]
    return render_template('result.html', hotels=results), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === TRANG CHI TIẾT KHÁCH SẠN ===
@app.route('/hotel/<name>')
def hotel_detail(name):
    hotel_data = hotels[hotels['name'] == name]
    if hotel_data.empty:
        return "<h3>Không tìm thấy khách sạn!</h3>", 404, {'Content-Type': 'text/html; charset=utf-8'}

    hotel = map_hotel_row(hotel_data.iloc[0].to_dict())
    reviews_df_local = read_csv_safe(REVIEWS_CSV)
    hotel_reviews = reviews_df_local[reviews_df_local['hotel_name'] == name].to_dict(orient='records')

    avg_rating = (
        round(sum(int(r['rating']) for r in hotel_reviews) / len(hotel_reviews), 1)
        if hotel_reviews else hotel.get('rating', 'Chưa có')
    )

    features = {
        "Buffet": yes_no_icon(hotel.get("buffet")),
        "Bể bơi": yes_no_icon(hotel.get("pool")),
        "Gần biển": yes_no_icon(hotel.get("sea_view") or hotel.get("sea")),
        "View biển": yes_no_icon(hotel.get("view")),
    }

    rooms = [
        {"type": "Phòng nhỏ", "price": round(float(hotel.get('price', 0)) * 1.0)},
        {"type": "Phòng đôi", "price": round(float(hotel.get('price', 0)) * 1.5)},
        {"type": "Phòng tổng thống", "price": round(float(hotel.get('price', 0)) * 2.5)},
    ]

    return render_template(
        'detail.html',
        hotel=hotel,
        features=features,
        rooms=rooms,
        reviews=hotel_reviews,
        avg_rating=avg_rating
    ), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === GỬI ĐÁNH GIÁ ===
@app.route('/review/<name>', methods=['POST'])
def add_review(name):
    user = request.form.get('user', 'Ẩn danh').strip()
    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()

    new_review = pd.DataFrame([{
        "hotel_name": name,
        "user": user,
        "rating": rating,
        "comment": comment
    }])

    df = read_csv_safe(REVIEWS_CSV)
    df = pd.concat([df, new_review], ignore_index=True)
    df.to_csv(REVIEWS_CSV, index=False, encoding="utf-8-sig")

    return redirect(url_for('hotel_detail', name=name))


# === TRANG CHỌN LOẠI PHÒNG ===
@app.route('/book/<name>')
def book_page(name):
    hotel_data = hotels[hotels['name'] == name]
    if hotel_data.empty:
        return "<h3>Không tìm thấy khách sạn!</h3>", 404, {'Content-Type': 'text/html; charset=utf-8'}

    hotel = map_hotel_row(hotel_data.iloc[0].to_dict())

    rooms = [
        {"type": "Phòng nhỏ", "price": float(hotel.get("price", 0)), "desc": "Phòng nhỏ gọn, tiện nghi, phù hợp 1 người."},
        {"type": "Phòng đôi", "price": float(hotel.get("price", 0)) * 1.5, "desc": "Phòng đôi, view đẹp, phù hợp cặp đôi."},
        {"type": "Phòng tổng thống", "price": float(hotel.get("price", 0)) * 3, "desc": "Phòng sang trọng, có hồ bơi riêng, dịch vụ cao cấp."}
    ]
    return render_template('book.html', hotel=hotel, rooms=rooms), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === TRANG ĐẶT PHÒNG ===
@app.route('/booking/<name>/<room_type>', methods=['GET', 'POST'])
def booking(name, room_type):
    hotel_data = hotels[hotels['name'] == name]
    if hotel_data.empty:
        return "<h3>Không tìm thấy khách sạn!</h3>", 404, {'Content-Type': 'text/html; charset=utf-8'}

    hotel = map_hotel_row(hotel_data.iloc[0].to_dict())

    if request.method == 'POST':
        info = {
            "hotel_name": name,
            "room_type": room_type,
            "price": float(request.form.get('price', hotel.get('price', 0))),
            "user_name": request.form['fullname'],
            "phone": request.form['phone'],
            "email": request.form.get('email', ''),
            "num_adults": int(request.form.get('adults', 1)),
            "num_children": int(request.form.get('children', 0)),
            "checkin_date": request.form['checkin'],
            "nights": 1,
            "special_requests": request.form.get('note', ''),
            "booking_time": datetime.now().isoformat()
        }

        df = pd.read_csv(BOOKINGS_CSV, encoding="utf-8-sig")
        df = pd.concat([df, pd.DataFrame([info])], ignore_index=True)
        df.to_csv(BOOKINGS_CSV, index=False, encoding="utf-8-sig")

        return render_template('success.html', info=info), 200, {'Content-Type': 'text/html; charset=utf-8'}

    return render_template('booking.html', hotel=hotel, room_type=room_type), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === TRANG GIỚI THIỆU ===
@app.route('/about')
def about_page():
    return render_template('about.html'), 200, {'Content-Type': 'text/html; charset=utf-8'}


# === KHỞI ĐỘNG ===
if __name__ == '__main__':
    app.run(debug=True)
