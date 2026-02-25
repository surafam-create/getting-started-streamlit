import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
import os
from datetime import datetime, timedelta, timezone
import requests
from geopy.geocoders import Nominatim
import urllib.parse 

# --- ตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Smart Logistics Pro", layout="wide", page_icon="🚚")

# ตัวแปรเก็บไฟล์ข้อมูล
DATA_FILE = 'saving_history.csv'
TRACKING_FILE = 'tracking_history.csv' 

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

# 2. ฟังก์ชันคำนวณต้นทุนแบบ Activity-Based Costing (ABC)
def calculate_market_price(distance_km, car_type, fuel_price_today):
    if "4" in car_type:
        driver_wage = 500          
        vehicle_depreciation = 150 
        fixed_cost = driver_wage + vehicle_depreciation
        fuel_efficiency = 12.0     
        maintenance_per_km = 1.0   
    else:
        driver_wage = 600          
        helper_wage = 350          
        vehicle_depreciation = 300 
        fixed_cost = driver_wage + helper_wage + vehicle_depreciation
        fuel_efficiency = 7.0      
        maintenance_per_km = 2.5   

    fuel_cost = (distance_km / fuel_efficiency) * fuel_price_today
    maintenance_cost = distance_km * maintenance_per_km
    total_base_cost = fixed_cost + fuel_cost + maintenance_cost
    
    return total_base_cost

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

    tz_thai = timezone(timedelta(hours=7))
    current_thai_time = datetime.now(tz_thai).strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "date": current_thai_time, 
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

# 7. ฟังก์ชันบันทึก Tracking สถานะคนขับ
def save_tracking_status(job_id, status):
    APP_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwHuMqah43jZlMFQumEfE7F22t4HCsnEPon8jOV9Y-WFaj9Yx8DhW1uex_DIQAZYowGbA/exec" 
    
    tz_thai = timezone(timedelta(hours=7))
    current_thai_time = datetime.now(tz_thai).strftime("%Y-%m-%d %H:%M:%S")

    data_to_send = {
        "date": current_thai_time,
        "job_id": job_id,
        "status": status
    }
    try:
        requests.post(APP_SCRIPT_URL, json=data_to_send)
    except:
        pass 

    new_data = pd.DataFrame({
        "Date_Time": [current_thai_time],
        "Driver_Job": [job_id],
        "Status": [status]
    })

    if os.path.exists(TRACKING_FILE):
        df = pd.read_csv(TRACKING_FILE)
    else:
        df = pd.DataFrame(columns=["Date_Time", "Driver_Job", "Status"])

    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(TRACKING_FILE, index=False, encoding='utf-8-sig')

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

st.sidebar.header("⚙️ ตั้งค่าระบบ (Daily Settings)")
st.sidebar.info("อัปเดตตัวแปรให้ตรงกับความเป็นจริง ณ วันที่ปฏิบัติงาน")
current_fuel_price = st.sidebar.number_input("⛽ ราคาน้ำมันดีเซลวันนี้ (บาท/ลิตร)", value=30.50, step=0.10)

st.title("🚚 Smart Logistics Platform")
st.caption("ระบบบริหารจัดการขนส่งครบวงจร (VRP + ABC Costing + Traffic Surcharge + Real-time Tracking)")

tab_file, tab_search, tab_driver, tab_history = st.tabs(["📂 จัดเส้นทางจากไฟล์", "🔍 ค้นหา/ระบุพิกัด", "📱 อัปเดตสถานะ (คนขับ)", "📊 ประวัติ & ดาวน์โหลด"])

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
                
                traffic_1 = st.selectbox("สภาพการจราจร / สภาพอากาศ", ["🟢 ปกติ (ถนนโล่ง)", "🟡 รถติดปานกลาง / ฝนตก", "🔴 รถติดหนัก (ช่วงเร่งด่วน)"], key="traf1")
                old_cost = st.number_input("ต้นทุนเดิม (บาท)", value=1200.0, key="old1")
                
                if st.button("🚀 คำนวณ (จากไฟล์)", type="primary"):
                    route, km, loc_dict = solve_vrp_from_df(depot, df)
                    
                    base_price = calculate_market_price(km, car_type, current_fuel_price)
                    
                    # --------- แก้ไขสูตรคำนวณเวลาใหม่ให้แม่นยำขึ้น ---------
                    # 1. ประเมินเวลาล้อหมุน: ความเร็วเฉลี่ย 50 กม./ชม. (1 กม. = 1.2 นาที)
                    driving_mins = km * 1.2
                    
                    # 2. ประเมินเวลาจอดลงของ: นับเฉพาะจุดลูกค้า (ตัดต้นทางและปลายทางออก) ให้เวลาจุดละ 15 นาที
                    num_dropoffs = max(0, len(route) - 2) 
                    dropoff_mins = num_dropoffs * 15
                    
                    # เวลารวมพื้นฐาน = เวลาขับรถ + เวลาลงของ
                    estimated_base_mins = driving_mins + dropoff_mins
                    # ----------------------------------------------------
                    
                    if "🟡" in traffic_1:
                        actual_mins = estimated_base_mins * 1.5
                    elif "🔴" in traffic_1:
                        actual_mins = estimated_base_mins * 2.0
                    else:
                        actual_mins = estimated_base_mins
                        
                    extra_time = actual_mins - estimated_base_mins
                    time_surcharge = extra_time * 2
                    final_cost = base_price + time_surcharge
                    
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
                    
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("ระยะทางรวม", f"{res['km']:.2f} กม.")
                    col_b.metric("เวลาจัดส่ง (ประเมิน)", f"{res['time']/60:.1f} ชม.")
                    col_c.metric("ราคาสุทธิ (ABC Costing)", f"{res['cost']:,.2f} บาท")
                    
                    st.caption(f"*(แบ่งเป็น: ต้นทุน Fixed+Variable {res['base_price']:,.0f} บ. + ค่าเสียเวลารถติด {res['surcharge']:,.0f} บ.)*")
                    
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
                
                base_price = calculate_market_price(km, car_type_2, current_fuel_price)
                
                if "🟡" in traffic_2:
                    actual_mins = base_mins * 1.5
                elif "🔴" in traffic_2:
                    actual_mins = base_mins * 2.5
                else:
                    actual_mins = base_mins
                    
                time_surcharge = (actual_mins - base_mins) * 2
                final_cost = base_price + time_surcharge
                
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
            st.caption(f"*(แบ่งเป็น: ต้นทุน Fixed+Variable {res['base_price']:,.0f} บ. + ค่าเสียเวลารถติด {res['surcharge']:,.0f} บ.)*")

# --- TAB 3: อัปเดตสถานะ (คนขับ) ---
with tab_driver:
    st.header("📱 อัปเดตสถานะการจัดส่ง (สำหรับพนักงานขับรถ)")
    st.info("💡 ให้คนขับรถเปิดหน้านี้บนมือถือ เพื่อกดรายงานสถานะให้แอดมินทราบแบบ Real-time")
    
    col_input, col_view = st.columns([1, 1.5])
    
    with col_input:
        job_id = st.text_input("📋 ระบุชื่องาน หรือ ชื่อคนขับ", placeholder="เช่น งานไปนครปฐม, น้าค่อม ทะเบียน บฉ1234")
        
        current_status = st.selectbox("🚦 สถานะปัจจุบัน", [
            "📦 กำลังขึ้นของ (At Depot)", 
            "🚚 กำลังเดินทาง (On the way)", 
            "📍 ถึงจุดหมาย (Arrived)", 
            "✅ ส่งมอบสำเร็จ (Delivered)",
            "❌ ส่งไม่สำเร็จ/ตีกลับ (Failed)"
        ])
        
        if st.button("📤 กดเพื่ออัปเดตสถานะ", type="primary", use_container_width=True):
            if job_id:
                save_tracking_status(job_id, current_status)
                st.success(f"บันทึกสถานะของ '{job_id}' เรียบร้อยแล้ว!")
            else:
                st.error("⚠️ กรุณากรอก 'ชื่องาน หรือ ชื่อคนขับ' ก่อนกดปุ่มครับ")
                
    with col_view:
        st.subheader("📋 กระดานติดตามสถานะ (Live Status)")
        if os.path.exists(TRACKING_FILE):
            track_df = pd.read_csv(TRACKING_FILE)
            latest_track = track_df.sort_values(by="Date_Time", ascending=False).head(10)
            st.dataframe(latest_track, use_container_width=True, hide_index=True)
            
            if st.button("🔄 รีเฟรชกระดาน"):
                st.rerun()
        else:
            st.write("ยังไม่มีข้อมูลการอัปเดตในวันนี้")

# --- TAB 4: ประวัติ ---
with tab_history:
    st.header("📊 ประวัติการใช้งาน & สถิติ")
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
            st.download_button("📥 ดาวน์โหลด CSV (คำนวณ)", csv_data, "history.csv", "text/csv", type="primary")
        with col_del:
            if st.button("🗑️ ล้างประวัติคำนวณ", type="secondary"):
                os.remove(DATA_FILE)
                st.rerun()
                
    else:
        st.info("ยังไม่มีประวัติคำนวณ")
        
    st.divider()
    st.subheader("📥 ดาวน์โหลดประวัติการส่งของ (Tracking)")
    if os.path.exists(TRACKING_FILE):
        track_csv = pd.read_csv(TRACKING_FILE).to_csv(index=False).encode('utf-8-sig')
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.download_button("📥 ดาวน์โหลด CSV (สถานะคนขับ)", track_csv, "tracking_data.csv", "text/csv")
        with col_t2:
            if st.button("🗑️ ล้างประวัติสถานะคนขับ"):
                os.remove(TRACKING_FILE)
                st.rerun()
    else:
        st.write("ยังไม่มีข้อมูลสถานะคนขับให้ดาวน์โหลด")