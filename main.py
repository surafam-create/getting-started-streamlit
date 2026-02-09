import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
import os
from datetime import datetime

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Daily VRP System", layout="wide", page_icon="🚚")
DATA_FILE = 'saving_history.csv'

# --- 1. ฟังก์ชันคำนวณระยะทาง (Logic เดิม) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c * 1.4 # Factor 1.4 เผื่อถนนคดเคี้ยว

# --- [ใหม่!] ฟังก์ชันคำนวณราคาตลาด (Real Market Price) ---
def calculate_market_price(distance_km, car_type):
    price = 0
    # --- กรณีรถกระบะ 4 ล้อ ---
    if "4" in car_type:
        base_price = 450  # ราคาเริ่มต้น
        if distance_km <= 40:
            price = base_price + (distance_km * 14)
        else:
            first_phase = 40 * 14
            remaining_dist = distance_km - 40
            price = base_price + first_phase + (remaining_dist * 10)
            
    # --- กรณีรถบรรทุก 6 ล้อ ---
    else:
        base_price = 1800 # ราคาเริ่มต้น
        if distance_km <= 80:
            price = base_price + (distance_km * 28)
        else:
            first_phase = 80 * 28
            remaining_dist = distance_km - 80
            price = base_price + first_phase + (remaining_dist * 22)
            
    return price

# --- 2. ฟังก์ชันจัดเส้นทาง (VRP) ---
def solve_vrp_from_df(depot_name, df_data):
    # แปลง Dataframe เป็น Dictionary เพื่อง่ายต่อการคำนวณ
    locations = {}
    for index, row in df_data.iterrows():
        locations[row['Location']] = [row['Latitude'], row['Longitude']]
    
    route = [depot_name]
    current_loc = depot_name
    
    # สร้างรายการจุดที่ต้องไป (ตัด Depot ออก)
    unvisited = [loc for loc in locations.keys() if loc != depot_name]
    
    total_dist = 0
    
    while unvisited:
        nearest_city = None
        min_dist = float('inf')
        
        curr_coords = locations[current_loc]
        
        for city in unvisited:
            dest_coords = locations[city]
            dist = calculate_distance(curr_coords[0], curr_coords[1], dest_coords[0], dest_coords[1])
            
            if dist < min_dist:
                min_dist = dist
                nearest_city = city
        
        if nearest_city:
            route.append(nearest_city)
            total_dist += min_dist
            current_loc = nearest_city
            unvisited.remove(nearest_city)
            
    # วนกลับ Depot
    start_coords = locations[depot_name]
    end_coords = locations[current_loc]
    total_dist += calculate_distance(end_coords[0], end_coords[1], start_coords[0], start_coords[1])
    route.append(depot_name)
    
    return route, total_dist, locations

# --- 3. ฟังก์ชันบันทึกประวัติ ---
def save_history(route_list, km, old_cost, new_cost):
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
    else:
        df = pd.DataFrame(columns=["Date", "Route", "Distance_KM", "Old_Cost", "New_Cost", "Saving"])
        
    new_data = pd.DataFrame({
        "Date": [datetime.now().strftime("%Y-%m-%d %H:%M")],
        "Route": [" -> ".join(route_list)],
        "Distance_KM": [km],
        "Old_Cost": [old_cost],
        "New_Cost": [new_cost],
        "Saving": [old_cost - new_cost]
    })
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)
    return df

# ================= หน้าจอแอป =================
st.title("🚛 ระบบจัดเส้นทางขนส่งประจำวัน (Daily Route)")

# ส่วนอัปโหลดไฟล์
st.info("💡 ขั้นตอนที่ 1: อัปโหลดไฟล์ Excel ที่มีรายชื่อลูกค้าของวันนี้")
uploaded_file = st.file_uploader("เลือกไฟล์ (.xlsx หรือ .csv)", type=['xlsx', 'csv'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        # [แก้ Error] บังคับให้ชื่อสถานที่ (Location) เป็นตัวหนังสือทั้งหมด
        df['Location'] = df['Location'].astype(str)
            
        # ตรวจสอบหัวตาราง
        required_cols = ['Location', 'Latitude', 'Longitude']
        if not all(col in df.columns for col in required_cols):
            st.error(f"❌ รูปแบบไฟล์ไม่ถูกต้อง! ต้องมีคอลัมน์: {required_cols}")
        else:
            st.success(f"✅ อ่านข้อมูลสำเร็จ: พบ {len(df)} สถานที่")
            st.dataframe(df.head())
            
            # เริ่มเข้าสู่หน้าคำนวณ
            tab1, tab2 = st.tabs(["🗺️ จัดเส้นทาง", "📊 สรุปผล"])
            
            with tab1:
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.subheader("ตั้งค่าการเดินรถ")
                    location_list = df['Location'].tolist()
                    depot = st.selectbox("📍 จุดเริ่มต้น (Depot)", location_list)
                    
                    car_type = st.radio("🚛 ประเภทรถ", ["รถกระบะ 4 ล้อ", "6 ล้อ"])
                    old_cost = st.number_input("งบประมาณ/ต้นทุนเดิม (บาท)", value=2000.0)
                    
                    if st.button("🚀 คำนวณเส้นทาง", type="primary"):
                        # 1. เรียกฟังก์ชันคำนวณเส้นทาง (เหมือนเดิม)
                        route, km, loc_dict = solve_vrp_from_df(depot, df)
                        
                        # 2. [เปลี่ยนใหม่!] ใช้ฟังก์ชันคำนวณราคาจริงแทนสูตรเก่า
                        new_cost = calculate_market_price(km, car_type)
                        
                        saving = old_cost - new_cost
                        
                        # 3. บันทึก (เหมือนเดิม)
                        save_history(route, km, old_cost, new_cost)
                        
                        # 4. เก็บค่าแสดงผล (เหมือนเดิม)
                        st.session_state['res'] = {
                            'route': route, 'km': km, 'cost': new_cost,
                            'saving': saving, 'locs': loc_dict
                        }

                with col2:
                    if 'res' in st.session_state:
                        res = st.session_state['res']
                        
                        # สร้างแผนที่
                        m = folium.Map(location=res['locs'][res['route'][0]], zoom_start=11)
                        route_coords = []
                        
                        for i, city in enumerate(res['route']):
                            coords = res['locs'][city]
                            route_coords.append(coords)
                            
                            icon_color = 'red' if i==0 or i==len(res['route'])-1 else 'blue'
                            folium.Marker(coords, popup=f"{i}. {city}", icon=folium.Icon(color=icon_color)).add_to(m)
                            
                        folium.PolyLine(route_coords, color='blue', weight=4).add_to(m)
                        st_folium(m, width=700)
                        
                        st.success(f"ระยะทางรวม: {res['km']:.2f} กม. | ต้นทุน: {res['cost']:,.2f} บาท")

            with tab2:
                if os.path.exists(DATA_FILE):
                    history_df = pd.read_csv(DATA_FILE)
                    st.write("ประวัติการใช้งานล่าสุด:")
                    st.dataframe(history_df.tail())
                    
                    total_save = history_df['Saving'].sum()
                    st.metric("💰 ประหยัดสะสมรวม", f"{total_save:,.2f} บาท")
                else:
                    st.info("ยังไม่มีประวัติ")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
else:
    st.warning("👈 กรุณาอัปโหลดไฟล์เพื่อเริ่มต้นใช้งาน")
    
    example_data = pd.DataFrame({
        'Location': ['คลังสินค้า', 'ลูกค้า A', 'ลูกค้า B'],
        'Latitude': [13.7563, 13.7200, 13.8000],
        'Longitude': [100.5018, 100.5500, 100.4500]
    })
    csv = example_data.to_csv(index=False).encode('utf-8')
    st.download_button("📥 ดาวน์โหลดไฟล์ตัวอย่าง (Template)", csv, "template.csv", "text/csv")