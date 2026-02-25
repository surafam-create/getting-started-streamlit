import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
import os
from datetime import datetime
import requests
from geopy.geocoders import Nominatim
import urllib.parse 

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Smart Logistics Pro", layout="wide", page_icon="🚚")
DATA_FILE = 'saving_history.csv'

# ================= โซนฟังก์ชันคำนวณ =================

# 1. ฟังก์ชันคำนวณระยะทาง
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c * 1.4

# 2. ฟังก์ชันคำนวณราคา (เฉพาะระยะทาง)
def calculate_market_price(distance_km, car_type):
    price = 0
    if "4" in car_type:
        base_price = 450
        if distance_km <= 40:
            price = base_price + (distance_km * 14)
        else:
            price = base_price + (40 * 14) + ((distance_km - 40) * 10)
    else:
        base_price = 1800
        if distance_km <= 80:
            price = base_price + (distance_km * 28)
        else:
            price = base_price + (80 * 28) + ((distance_km - 80) * 22)
    return price

# 3. ฟังก์ชัน VRP (จัดเส้นทาง)
def solve_vrp_from_df(depot_name, df_data):
    locations = {}
    for index, row in df_data.iterrows():
        locations[row['Location']] = [row['Latitude'], row['Longitude']]
    
    route = [depot_name]
    current_loc = depot_name
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
            
    start_coords = locations[depot_name]
    end_coords = locations[current_loc]
    total_dist += calculate_distance(end_coords[0], end_coords[1], start_coords[0], start_coords[1])
    route.append(depot_name)
    return route, total_dist, locations

# 4. ฟังก์ชัน Geocoding
def get_lat_lon(location_name):
    geolocator = Nominatim(user_agent="logistics_student_project_66")
    try:
        location = geolocator.geocode(location_name + ", Thailand", timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except:
        return None, None

# 5. ฟังก์ชัน OSRM
def get_osrm_route(coord1, coord2):
    url = f"http://router.project-osrm.org/route/v1/driving/{coord1[1]},{coord1[0]};{coord2[1]},{coord2[0]}?overview=full&geometries=geojson"
    try:
        r = requests.get(url)
        res = r.json()
        routes = res['routes'][0]
        return routes['geometry'], routes['distance']/1000, routes['duration']/60
    except:
        return None, 0, 0

# 6. ฟังก์ชันบันทึกประวัติ (เชื่อมต่อ Google Sheets)
def save_history(route_str, km, old_cost, new_cost):
    APP_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwHuMqah43jZlMFQumEfE7F22t4HCsnEPon8jOV9Y-WFaj9Yx8DhW1uex_DIQAZYowGbA/exec" 

    data = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "route": route_str,
        "km": km,
        "old_cost": old_cost,
        "new_cost": new_cost,
        "saving": old_cost - new_cost
    }

    try:
        if "script.google.com" in APP_SCRIPT_URL:
            response = requests.post(APP_SCRIPT_URL, json=data)
            if response.status_code == 200:
                st.toast('✅ บันทึกข้อมูลลง Google Sheets แล้ว!', icon='☁️')
            else:
                st.toast(f'⚠️ Google แจ้งว่า: {response.text}', icon='⚠️')
    except Exception as e:
        st.error(f"❌ เชื่อมต่อ Google ไม่ได้: {e}")

    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
    else:
        df = pd.DataFrame(columns=["Date", "Route", "Distance_KM", "Old_Cost", "New_Cost", "Saving"])
    
    new_row = pd.DataFrame([{
        "Date": data["date"], "Route": data["route"], "Distance_KM": data["km"],
        "Old_Cost": data["old_cost"], "New_Cost": data["new_cost"], "Saving": data["saving"]
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')

# --- ฟังก์ชันสร้างลิงก์ Google Maps ---
def create_gmaps_link(route_list, loc_dict):
    if not route_list: return None
    origin = loc_dict[route_list[0]]
    origin_str = f"{origin[0]},{origin[1]}"
    dest = loc_dict[route_list[-1]]
    dest_str = f"{dest[0]},{dest[1]}"
    
    waypoints = route_list[1:-1]
    waypoint_strs = []
    for wp in waypoints:
        coords = loc_dict[wp]
        waypoint_strs.append(f"{coords[0]},{coords[1]}")
    
    waypoints_param = "|".join(waypoint_strs)
    base_url = "https://www.google.com/maps/dir/?api=1"
    full_url = f"{base_url}&origin={origin_str}&destination={dest_str}&waypoints={waypoints_param}&travelmode=driving"
    return full_url

# ================= หน้าจอแอป (UI) =================
st.title("🚚 Smart Logistics Platform")
st.caption("ระบบบริหารจัดการขนส่งครบวงจร (VRP + Hybrid Search + Traffic Cost)")

tab_file, tab_search, tab_history = st.tabs(["📂 จัดเส้นทางจากไฟล์", "🔍 ค้นหา/ระบุพิกัด", "📊 ประวัติ & ดาวน์โหลด"])

# --- TAB 1: จัดเส้นทาง ---
with tab_file:
    st.header("จัดเส้นทางหลายจุด (Batch Upload)")
    st.info("💡 อัปโหลดไฟล์ Excel/CSV ที่มีรายชื่อลูกค้าเพื่อจัดเส้นทางอัตโนมัติ")
    
    uploaded_file = st.file_uploader("เลือกไฟล์ (.xlsx หรือ .csv)", type=['xlsx', 'csv'], key="file_upload")

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            df['Location'] = df['Location'].astype(str)
            
            c1, c2 = st.columns([1, 2])
            with c1:
                location_list = df['Location'].tolist()
                depot = st.selectbox("จุดเริ่มต้น", location_list)
                car_type = st.radio("ประเภทรถ", ["รถกระบะ 4 ล้อ", "6 ล้อ"], key="car1")
                
                # [ใหม่] เพิ่มตัวเลือกสภาพจราจร
                traffic_1 = st.selectbox("สภาพการจราจร / สภาพอากาศ", ["🟢 ปกติ (ถนนโล่ง)", "🟡 รถติดปานกลาง / ฝนตก", "🔴 รถติดหนัก (ช่วงเร่งด่วน)"], key="traf1")
                old_cost = st.number_input("ต้นทุนเดิม (บาท)", value=1200.0, key="old1") # ตั้งค่าเริ่มต้น 1200 ตามที่คุณลงพื้นที่
                
                if st.button("🚀 คำนวณ (จากไฟล์)", type="primary"):
                    route, km, loc_dict = solve_vrp_from_df(depot, df)
                    
                    # 1. คำนวณราคาฐาน (จากระยะทาง)
                    base_price = calculate_market_price(km, car_type)
                    
                    # 2. คำนวณค่าเสียเวลา (Time Surcharge)
                    # ประเมินเวลาวิ่งแบบถนนโล่ง: ความเร็วเฉลี่ย 40 กม./ชม. (1 กม. = 1.5 นาที) + จอดจุดละ 15 นาที
                    estimated_base_mins = (km * 1.5) + (len(route) * 15) 
                    
                    if "🟡" in traffic_1:
                        actual_mins = estimated_base_mins * 1.5  # ช้าลง 50%
                    elif "🔴" in traffic_1:
                        actual_mins = estimated_base_mins * 2.0  # ช้าลง 100%
                    else:
                        actual_mins = estimated_base_mins
                        
                    # คิดค่าเสียเวลาส่วนเกิน นาทีละ 2 บาท
                    extra_time = actual_mins - estimated_base_mins
                    time_surcharge = extra_time * 2
                    
                    # 3. ราคาสุทธิ
                    final_cost = base_price + time_surcharge
                    
                    # บันทึกข้อมูล
                    save_history(" -> ".join(route), km, old_cost, final_cost)
                    gmaps_link = create_gmaps_link(route, loc_dict)
                    
                    st.session_state['res_file'] = {
                        'route': route, 'km': km, 'cost': final_cost, 'locs': loc_dict,
                        'gmaps': gmaps_link, 'base_price': base_price, 'surcharge': time_surcharge,
                        'time': actual_mins
                    }

            with c2:
                if 'res_file' in st.session_state:
                    res = st.session_state['res_file']
                    
                    st.success(f"✅ จัดเส้นทางสำเร็จ! ({len(res['route'])-2} จุดส่ง)")
                    st.link_button("🗺️ เปิดนำทางใน Google Maps", res['gmaps'], type="primary", use_container_width=True)
                    
                    m = folium.Map(location=res['locs'][res['route'][0]], zoom_start=11)
                    route_coords = [res['locs'][city] for city in res['route']]
                    for i, city in enumerate(res['route']):
                        folium.Marker(res['locs'][city], popup=f"{i}. {city}", 
                                      icon=folium.Icon(color='red' if i==0 else 'blue', icon='info-sign')).add_to(m)
                    folium.PolyLine(route_coords, color='blue', weight=4).add_to(m)
                    st_folium(m, width=700, key="map1")
                    
                    st.info(f"📍 ลำดับการส่ง: {' -> '.join(res['route'])}")
                    
                    # แสดงผลแบบแยกรายละเอียดให้เห็นชัดเจน
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("ระยะทางรวม", f"{res['km']:.2f} กม.")
                    col_b.metric("เวลาจัดส่ง (ประเมิน)", f"{res['time']/60:.1f} ชม.")
                    col_c.metric("ราคาสุทธิ", f"{res['cost']:,.2f} บาท")
                    
                    st.caption(f"*(แบ่งเป็น: ราคาตามระยะทาง {res['base_price']:,.0f} บ. + ค่าเสียเวลารถติด {res['surcharge']:,.0f} บ.)*")
                    
        except Exception as e:
            st.error(f"Error: {e}")
            
    else:
        st.warning("👉 กรุณาอัปโหลดไฟล์เพื่อเริ่มต้นใช้งาน")
        example_data = pd.DataFrame({
            'Location': ['คลังสินค้า', 'ลูกค้า A', 'ลูกค้า B'],
            'Latitude': [13.7563, 13.7200, 13.8000],
            'Longitude': [100.5018, 100.5500, 100.4500]
        })
        csv_template = example_data.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 ดาวน์โหลดไฟล์ตัวอย่าง", csv_template, "template.csv", "text/csv", icon="📄")

# --- TAB 2: Hybrid Search ---
with tab_search:
    st.header("เช็คราคาจุดต่อจุด")
    col1, col2 = st.columns([1, 2])
    with col1:
        input_method = st.radio("วิธีระบุตำแหน่ง:", ["🔍 ค้นหาจากชื่อ", "🌐 ระบุพิกัด GPS"])
        start_lat, start_lon, end_lat, end_lon = None, None, None, None
        start_name, end_name = "", ""
        start_name_in, end_name_in = "", ""

        if input_method == "🔍 ค้นหาจากชื่อ":
            start_name_in = st.text_input("ชื่อจุดเริ่มต้น", "ตลาดไท")
            end_name_in = st.text_input("ชื่อจุดปลายทาง", "เซ็นทรัล เวสต์เกต")
        else:
            c_lat1, c_lon1 = st.columns(2)
            start_lat = c_lat1.number_input("Lat ต้นทาง", 13.0000, format="%.4f")
            start_lon = c_lon1.number_input("Lon ต้นทาง", 100.0000, format="%.4f")
            c_lat2, c_lon2 = st.columns(2)
            end_lat = c_lat2.number_input("Lat ปลายทาง", 13.0000, format="%.4f")
            end_lon = c_lon2.number_input("Lon ปลายทาง", 100.0000, format="%.4f")

        car_type_2 = st.radio("ประเภทรถ", ["รถกระบะ 4 ล้อ", "6 ล้อ"], key="car2")
        
        # [ใหม่] เพิ่มตัวเลือกสภาพจราจร
        traffic_2 = st.selectbox("สภาพการจราจร / สภาพอากาศ", ["🟢 ปกติ (ถนนโล่ง)", "🟡 รถติดปานกลาง / ฝนตก", "🔴 รถติดหนัก (ช่วงเร่งด่วน)"], key="traf2")
        old_cost_2 = st.number_input("ต้นทุนเดิม (บาท)", value=1000.0, key="old2")

        if st.button("🚀 คำนวณ (ค้นหา)", type="primary"):
            if input_method == "🔍 ค้นหาจากชื่อ":
                with st.spinner('กำลังค้นหาพิกัด...'):
                    start_lat, start_lon = get_lat_lon(start_name_in)
                    end_lat, end_lon = get_lat_lon(end_name_in)
                    start_name, end_name = start_name_in, end_name_in
            else:
                start_name, end_name = f"GPS:{start_lat},{start_lon}", f"GPS:{end_lat},{end_lon}"

            if start_lat and end_lat:
                geo_path, km, base_mins = get_osrm_route((start_lat, start_lon), (end_lat, end_lon))
                
                # คำนวณราคาฐาน
                base_price = calculate_market_price(km, car_type_2)
                
                # คำนวณค่าเสียเวลา (Time Surcharge)
                if "🟡" in traffic_2:
                    actual_mins = base_mins * 1.5
                elif "🔴" in traffic_2:
                    actual_mins = base_mins * 2.5
                else:
                    actual_mins = base_mins
                    
                time_surcharge = (actual_mins - base_mins) * 2 # คิดเพิ่มนาทีละ 2 บาท
                final_cost = base_price + time_surcharge
                
                # บันทึกข้อมูล
                save_history(f"{start_name}->{end_name}", km, old_cost_2, final_cost)
                
                gmaps_link_2 = f"https://www.google.com/maps/dir/?api=1&origin={start_lat},{start_lon}&destination={end_lat},{end_lon}&travelmode=driving"

                st.session_state['res_search'] = {
                    'start': [start_lat, start_lon], 'end': [end_lat, end_lon],
                    'km': km, 'mins': actual_mins, 'cost': final_cost, 'path': geo_path,
                    'names': [start_name, end_name], 'gmaps': gmaps_link_2,
                    'base_price': base_price, 'surcharge': time_surcharge
                }
            else:
                st.error("❌ หาพิกัดไม่เจอ")

    with col2:
        if 'res_search' in st.session_state:
            res = st.session_state['res_search']
            st.link_button("🗺️ นำทางด้วย Google Maps", res['gmaps'], type="primary", use_container_width=True)
            
            m2 = folium.Map(location=res['start'], zoom_start=12)
            if res['path']:
                folium.GeoJson(res['path'], style_function=lambda x: {'color':'green', 'weight':5}).add_to(m2)
            folium.Marker(res['start'], popup=res['names'][0], icon=folium.Icon(color='green', icon='play')).add_to(m2)
            folium.Marker(res['end'], popup=res['names'][1], icon=folium.Icon(color='red', icon='stop')).add_to(m2)
            st_folium(m2, width=700, height=500, key="map2")
            
            st.success(f"ระยะทาง: {res['km']:.2f} กม. | เวลาขับรถ: {res['mins']:.0f} นาที | ราคาสุทธิ: {res['cost']:,.2f} บาท")
            st.caption(f"*(แบ่งเป็น: ราคาตามระยะทาง {res['base_price']:,.0f} บ. + ค่าเสียเวลารถติด {res['surcharge']:,.0f} บ.)*")

# --- TAB 3: ประวัติ ---
with tab_history:
    st.header("📊 ประวัติการใช้งาน")
    if os.path.exists(DATA_FILE):
        history_df = pd.read_csv(DATA_FILE)
        c1, c2, c3 = st.columns(3)
        c1.metric("📝 จำนวนงาน", f"{len(history_df)} งาน")
        c2.metric("💰 ประหยัดสะสม", f"{history_df['Saving'].sum():,.0f} บาท")
        c3.metric("🛣️ ระยะทางรวม", f"{history_df['Distance_KM'].sum():,.1f} กม.")
        
        st.dataframe(history_df.tail(10))
        
        csv_data = history_df.to_csv(index=False).encode('utf-8-sig')
        col_down, col_del = st.columns(2)
        with col_down:
            st.download_button("ดาวน์โหลด CSV", csv_data, "history.csv", "text/csv", type="primary", icon="💾")
        with col_del:
            if st.button("ล้างประวัติ", type="secondary", icon="🗑️"):
                os.remove(DATA_FILE)
                st.rerun()
    else:
        st.info("ยังไม่มีประวัติ")