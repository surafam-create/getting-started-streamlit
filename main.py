import streamlit as st
import random

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="ระบบคำนวณต้นทุนขนส่ง", page_icon="🚚")

# --- ฟังก์ชันจำลองระยะทาง (Mock Data) ---
def get_mock_distance(origin, dest):
    return random.randint(10, 500) # สุ่มระยะทางมาโชว์ก่อน

# --- ฟังก์ชันคำนวณเงิน ---
def calculate_cost(distance, car_type):
    if car_type == "รถกระบะ 4 ล้อ":
        base_price = 500
        per_km = 15
    else: # รถ 6 ล้อ
        base_price = 1500
        per_km = 25
        
    return base_price + (distance * per_km)

# --- ส่วนหน้าจอ UI ---
st.title("🚚 โปรแกรมคำนวณต้นทุนขนส่งสินค้า")

col1, col2 = st.columns(2)

with col1:
    st.header("📝 ข้อมูล")
    origin = st.text_input("ต้นทาง", "กรุงเทพ")
    dest = st.text_input("ปลายทาง", "เชียงใหม่")
    car_type = st.radio("เลือกประเภทรถ", ["รถกระบะ 4 ล้อ", "รถบรรทุก 6 ล้อ"])
    
    btn = st.button("คำนวณราคา 🚀", type="primary")

with col2:
    st.header("📊 ผลลัพธ์")
    if btn:
        dist = get_mock_distance(origin, dest)
        cost = calculate_cost(dist, car_type)
        
        st.metric("ระยะทางประมาณ", f"{dist} กม.")
        st.metric("ค่าขนส่งประเมิน", f"{cost:,} บาท")
        st.success(f"เส้นทาง: {origin} -> {dest}")