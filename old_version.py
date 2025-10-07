import streamlit as st
import pandas as pd
from datetime import datetime, date, timezone, timedelta
import calendar
import json
import os
from cryptography.fernet import Fernet

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="Shift Roster & Holiday Tracker",
    page_icon="🗓️",
    layout="wide"
)

# --- SECURITY & DATA PERSISTENCE ---
DATA_FILE = "roster_data.json"
KEY_FILE = "secret.key"
PASSWORD_FILE = "admin_secret.key"

def generate_key():
    """Generates a new encryption key and saves it to a file."""
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    """Loads the encryption key from the key file. Generates a new one if it doesn't exist."""
    if not os.path.exists(KEY_FILE):
        return generate_key()
    with open(KEY_FILE, "rb") as key_file:
        return key_file.read()

def save_password(password):
    """Encrypts and saves the admin password."""
    key = load_key()
    fernet = Fernet(key)
    encrypted_password = fernet.encrypt(password.encode())
    with open(PASSWORD_FILE, "wb") as password_file:
        password_file.write(encrypted_password)

def load_password():
    """Loads and decrypts the admin password. Sets a default if it doesn't exist."""
    if not os.path.exists(PASSWORD_FILE):
        save_password("admin123")  # Set default password on first run
    
    key = load_key()
    fernet = Fernet(key)
    with open(PASSWORD_FILE, "rb") as password_file:
        encrypted_password = password_file.read()
    
    decrypted_password = fernet.decrypt(encrypted_password).decode()
    return decrypted_password

def save_data():
    """Saves the current session state (excluding password) to a JSON file."""
    rosters_json = {
        key: df.to_json(orient='split')
        for key, df in st.session_state.rosters.items()
    }
    data_to_save = {
        'teams': st.session_state.teams,
        'holidays': [{'name': h['name'], 'date': h['date'].isoformat()} for h in st.session_state.holidays],
        'rosters': rosters_json
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)

def load_data():
    """Loads the application state from a JSON file if it exists, overriding defaults."""
    st.session_state.admin_password = load_password()
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                st.session_state.teams = data.get('teams', st.session_state.teams)
                
                loaded_holidays = data.get('holidays', [])
                st.session_state.holidays = [{'name': h['name'], 'date': date.fromisoformat(h['date'])} for h in loaded_holidays]

                rosters_json = data.get('rosters', {})
                st.session_state.rosters = {}
                for key, df_json in rosters_json.items():
                    df = pd.read_json(df_json, orient='split')
                    st.session_state.rosters[key] = df
            except (json.JSONDecodeError, KeyError):
                # If file is corrupt, defaults set during initialization will be used.
                pass

# --- INITIALIZATION & SESSION STATE ---

# This new initialization logic is more robust. It ensures that all necessary
# session state variables have a default value on every script run. This prevents
# errors if a user's session is from an older version of the app that was missing a key.
defaults = {
    'teams': {'Team Avengers': [f'Avenger {i+1}' for i in range(3)], 'Team Justice': [f'Justice {i+1}' for i in range(2)]},
    'holidays': [],
    'rosters': {},
    'admin_password': "",
    'view': 'Employee View',
    'authenticated': False,
    'selected_team': 'All Teams'
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Data is loaded from files only once per session to avoid overwriting user changes.
if 'data_loaded' not in st.session_state:
    load_data()
    st.session_state.data_loaded = True

# Pre-defined shift options
SHIFT_OPTIONS = ['General', 'Morning', 'Evening', 'Night', 'Off', 'Holiday']
DEFAULT_SHIFT = 'General'

# --- HELPER FUNCTIONS ---

def get_all_employees():
    """Returns a flat list of all employees from all teams."""
    all_employees = []
    for team_members in st.session_state.teams.values():
        all_employees.extend(team_members)
    return all_employees

def generate_roster(year, month, employees, holidays):
    """Generates a fresh roster for a given month and year."""
    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)] # Use string columns
    
    if not employees:
        return pd.DataFrame()

    new_roster = pd.DataFrame(index=employees, columns=days).fillna(DEFAULT_SHIFT)

    for day in days:
        current_date = datetime(year, month, int(day)).date() # Convert back to int for date logic
        if current_date.weekday() >= 5: # Saturday or Sunday
            new_roster[day] = 'Off'
        
        for holiday in holidays:
            if current_date == holiday['date']:
                new_roster[day] = 'Holiday'
        
    return new_roster

def generate_roster_from_previous(previous_roster, year, month, employees, holidays):
    """Generates a new roster using the previous month's roster as a template."""
    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)] # Use string columns

    if not employees:
        return pd.DataFrame()

    new_roster = pd.DataFrame(index=employees, columns=days)
    
    common_employees = previous_roster.index.intersection(employees)
    for day in days:
        if day in previous_roster.columns and not common_employees.empty:
            new_roster.loc[common_employees, day] = previous_roster.loc[common_employees, day]

    new_roster.fillna(DEFAULT_SHIFT, inplace=True)

    for day in days:
        current_date = datetime(year, month, int(day)).date() # Convert back to int for date logic
        if current_date.weekday() >= 5: # Saturday or Sunday
            new_roster[day] = 'Off'
        for holiday in holidays:
            if current_date == holiday['date']:
                new_roster[day] = 'Holiday'
    
    return new_roster

def update_roster_with_new_employees(existing_roster, new_employees, year, month, holidays):
    """Updates an existing roster to reflect changes in the employee list, preserving existing data."""
    if not new_employees:
        return pd.DataFrame()

    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)] # Use string columns
    
    updated_roster = pd.DataFrame(index=new_employees, columns=days)
    
    for employee in new_employees:
        updated_roster.loc[employee] = DEFAULT_SHIFT

    for day in days:
        current_date = datetime(year, month, int(day)).date() # Convert back to int for date logic
        if current_date.weekday() >= 5: # Saturday or Sunday
            updated_roster[day] = 'Off'
        for holiday in holidays:
            if current_date == holiday['date']:
                updated_roster[day] = 'Holiday'
    
    common_employees = existing_roster.index.intersection(new_employees)
    
    if not common_employees.empty:
        updated_roster.loc[common_employees, :] = existing_roster.loc[common_employees, :]
        
    return updated_roster

def style_roster(df):
    """Applies color coding to the roster DataFrame for display."""
    def color_cells(val):
        color_map = {
            'General': '#D4EDDA',
            'Morning': '#FFF3CD',
            'Evening': '#FFF3CD',
            'Night': '#D6D1F5',
            'Off': '#F8D7DA',
            'Holiday': '#D1ECF1'
        }
        color = color_map.get(val, 'white')
        return f'background-color: {color}; color: black;'
    
    df_to_style = df.copy()
    day_headers = {day: f"{day} ({calendar.day_abbr[datetime(st.session_state.year, st.session_state.month, int(day)).weekday()]})" for day in df_to_style.columns}
    return df_to_style.rename(columns=day_headers).style.apply(lambda s: s.map(color_cells))

def display_employee_details(employee_name):
    """Displays the upcoming schedule for a selected employee."""
    st.header(f"Schedule for {employee_name}")
    
    today = datetime.now().date()
    
    # --- Upcoming Shifts ---
    st.subheader("Upcoming Shifts")
    
    upcoming_shifts = []
    
    # Sort roster keys to process them chronologically
    sorted_roster_keys = sorted(st.session_state.rosters.keys())
    
    for key in sorted_roster_keys:
        roster_year, roster_month = map(int, key.split('-'))
        
        # Check if the month is current or in the future
        if roster_year > today.year or (roster_year == today.year and roster_month >= today.month):
            roster_df = st.session_state.rosters[key]
            
            if employee_name in roster_df.index:
                employee_shifts = roster_df.loc[employee_name]
                for day_str, shift in employee_shifts.items():
                    day = int(day_str)
                    try:
                        shift_date = date(roster_year, roster_month, day)
                        if shift_date >= today:
                            upcoming_shifts.append({
                                "Date": shift_date,
                                "Day": shift_date.strftime("%A"),
                                "Shift": shift
                            })
                    except ValueError:
                        continue
    
    if upcoming_shifts:
        shifts_df = pd.DataFrame(upcoming_shifts)
        shifts_df = shifts_df.sort_values(by="Date").reset_index(drop=True)
        st.dataframe(shifts_df, use_container_width=True)
    else:
        st.info("No upcoming shifts found for this employee.")

    # --- Upcoming Holidays ---
    st.subheader("Upcoming Company Holidays")
    
    upcoming_holidays = []
    for holiday in st.session_state.holidays:
        if holiday['date'] >= today:
            upcoming_holidays.append({
                "Date": holiday['date'],
                "Holiday Name": holiday['name']
            })
    
    if upcoming_holidays:
        holidays_df = pd.DataFrame(upcoming_holidays)
        holidays_df = holidays_df.sort_values(by="Date").reset_index(drop=True)
        st.dataframe(holidays_df, use_container_width=True)
    else:
        st.info("No upcoming holidays scheduled.")

# --- SIDEBAR ---
st.sidebar.image("https://www.roche.com/dam/jcr:17d8536e-f78f-4326-afdd-f7c3272d1a1e/roche-logo-2023.png", width=150)
st.sidebar.title("🗓️ Shift Roster Controls")
st.sidebar.radio("Select View", ['Employee View', 'Admin View'], key='view', on_change=lambda: st.session_state.update(authenticated=False))
st.sidebar.markdown("---")

# --- Admin View Logic ---
if st.session_state.view == 'Admin View':
    if not st.session_state.authenticated:
        st.sidebar.header("Admin Login")
        password = st.sidebar.text_input("Enter Admin Password", type="password", key="admin_password_input")
        if st.sidebar.button("Login"):
            if password == st.session_state.admin_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.sidebar.error("Incorrect password.")
    else:
        st.sidebar.header("Admin Panel")
        
        selected_year = st.session_state.get('year', datetime.now().year)
        selected_month_num = st.session_state.get('month', datetime.now().month)

        def propagate_employee_changes(change_year, change_month):
            """Updates all rosters from the change date forward with the new employee list."""
            change_date = datetime(change_year, change_month, 1).date()
            all_employees = get_all_employees()
            
            for key in list(st.session_state.rosters.keys()):
                roster_year, roster_month = map(int, key.split('-'))
                roster_date = datetime(roster_year, roster_month, 1).date()

                if roster_date >= change_date:
                    existing_df = st.session_state.rosters[key]
                    st.session_state.rosters[key] = update_roster_with_new_employees(
                        existing_df, all_employees, roster_year, roster_month, st.session_state.holidays
                    )
        
        with st.sidebar.expander("Manage Teams", expanded=False):
            new_team_name = st.text_input("New Team Name")
            if st.button("Add Team"):
                if new_team_name and new_team_name not in st.session_state.teams:
                    st.session_state.teams[new_team_name] = []
                    save_data()
                    st.rerun()
            
            team_to_delete = st.selectbox("Select team to delete", options=list(st.session_state.teams.keys()))
            if st.button("Delete Team"):
                if team_to_delete and not st.session_state.teams[team_to_delete]:
                    del st.session_state.teams[team_to_delete]
                    save_data()
                    st.rerun()
                else:
                    st.warning("Cannot delete a team with members.")

        with st.sidebar.expander("Manage Employees", expanded=True):
            for team, members in st.session_state.teams.items():
                st.markdown(f"**{team}**")
                for i, emp in enumerate(members):
                    col1, col2 = st.columns([0.8, 0.2])
                    col1.text(f"  - {emp}")
                    if col2.button("❌", key=f"del_emp_{team}_{i}", help=f"Remove {emp}"):
                        st.session_state.teams[team].pop(i)
                        propagate_employee_changes(selected_year, selected_month_num)
                        save_data()
                        st.rerun()
            
            st.markdown("---")
            new_emp_name = st.text_input("New Employee Name", key="new_emp_name")
            team_to_add_to = st.selectbox("Select Team for New Employee", options=list(st.session_state.teams.keys()))
            if st.button("Add Employee"):
                if new_emp_name and team_to_add_to and new_emp_name not in get_all_employees():
                    st.session_state.teams[team_to_add_to].append(new_emp_name)
                    propagate_employee_changes(selected_year, selected_month_num)
                    save_data()
                    st.rerun()
        
        with st.sidebar.expander("Manage Holidays"):
            holiday_name = st.text_input("Holiday Name")
            holiday_date = st.date_input("Holiday Date", min_value=datetime(selected_year, 1, 1), max_value=datetime(selected_year, 12, 31))

            if st.button("Add Holiday"):
                if holiday_name:
                    if any(h['date'] == holiday_date for h in st.session_state.holidays):
                        st.warning("This date is already a holiday.")
                    else:
                        st.session_state.holidays.append({'name': holiday_name, 'date': holiday_date})
                        holiday_roster_key = f"{holiday_date.year}-{holiday_date.month}"
                        if holiday_roster_key in st.session_state.rosters:
                            roster_to_update = st.session_state.rosters[holiday_roster_key]
                            day_of_holiday = str(holiday_date.day)
                            if day_of_holiday in roster_to_update.columns:
                                roster_to_update[day_of_holiday] = 'Holiday'
                        save_data()
                        st.rerun()
        
        with st.sidebar.expander("Change Admin Password"):
            new_password = st.text_input("New Password", type="password", key="new_pass")
            confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_pass")
            if st.button("Change Password"):
                if new_password and new_password == confirm_password:
                    save_password(new_password)
                    st.session_state.admin_password = new_password
                    st.sidebar.success("Password changed successfully!")
        
        st.sidebar.markdown("---")
        if st.sidebar.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

# --- Shared Controls ---
st.sidebar.markdown("---")
st.sidebar.header("Select Roster Period")
current_year = datetime.now().year
year_index = list(range(current_year - 2, current_year + 3)).index(st.session_state.get('year', current_year))
month_index = st.session_state.get('month', datetime.now().month) - 1

selected_year = st.sidebar.selectbox("Year", list(range(current_year - 2, current_year + 3)), index=year_index, key='year_select')
selected_month_num = st.sidebar.selectbox("Month", list(range(1, 13)), format_func=lambda x: calendar.month_name[x], index=month_index, key='month_select')

st.session_state.year = selected_year
st.session_state.month = selected_month_num
roster_key = f"{selected_year}-{selected_month_num}"

# This logic now uses ALL employees to ensure data integrity
all_employees_list = get_all_employees()

if roster_key not in st.session_state.rosters:
    prev_month_date = (datetime(selected_year, selected_month_num, 1) - pd.DateOffset(months=1))
    prev_roster_key = f"{prev_month_date.year}-{prev_month_date.month}"
    
    if prev_roster_key in st.session_state.rosters:
        previous_roster = st.session_state.rosters[prev_roster_key]
        st.session_state.rosters[roster_key] = generate_roster_from_previous(
            previous_roster, selected_year, selected_month_num, all_employees_list, st.session_state.holidays
        )
    else:
        st.session_state.rosters[roster_key] = generate_roster(
            selected_year, selected_month_num, all_employees_list, st.session_state.holidays
        )
    save_data()

# Determine which employees to show based on the filter
if st.session_state.selected_team == 'All Teams':
    employees_to_display = all_employees_list
else:
    employees_to_display = st.session_state.teams.get(st.session_state.selected_team, [])


st.sidebar.markdown("---")
st.sidebar.header("Search Employee Schedule")
search_options = ["-- Select Employee --"] + employees_to_display # Use filtered list
selected_employee = st.sidebar.selectbox("Select an employee", options=search_options, key="search_selection")

st.sidebar.markdown("---")
st.sidebar.header("Holiday Tracker")
if st.session_state.holidays:
    st.sidebar.markdown("**Current Holidays:**")
    for i, holiday in enumerate(list(st.session_state.holidays)):
        if st.session_state.view == 'Admin View' and st.session_state.authenticated:
            col1, col2 = st.sidebar.columns([3, 1])
            col1.write(f"• {holiday['name']} ({holiday['date'].strftime('%d %b %Y')})")
            if col2.button("Del", key=f"del_holiday_{i}", help="Delete this holiday"):
                deleted_holiday_date = st.session_state.holidays.pop(i)['date']
                holiday_roster_key = f"{deleted_holiday_date.year}-{deleted_holiday_date.month}"
                if holiday_roster_key in st.session_state.rosters:
                    roster_to_update = st.session_state.rosters[holiday_roster_key]
                    day_of_holiday = str(deleted_holiday_date.day)
                    if day_of_holiday in roster_to_update.columns:
                        if deleted_holiday_date.weekday() >= 5:
                            roster_to_update[day_of_holiday] = 'Off'
                        else:
                            roster_to_update[day_of_holiday] = DEFAULT_SHIFT
                save_data()
                st.rerun()
        else:
            st.sidebar.write(f"• {holiday['name']} ({holiday['date'].strftime('%d %b %Y')})")
else:
    st.sidebar.info("No holidays added.")

# --- MAIN PAGE ---
col1, col2 = st.columns([2, 1])

with col1:
    if st.session_state.search_selection == "-- Select Employee --":
        st.title(f"🏢 Shift Roster for {calendar.month_name[selected_month_num]} {selected_year}")
    else:
        st.title(f"🔎 Search Results")

with col2:
    team_options = ['All Teams'] + list(st.session_state.teams.keys())
    st.selectbox("Filter by Team", options=team_options, key='selected_team')
    
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(ist_tz)
    st.markdown(f"""
    <div style="text-align: right; color: grey; margin-top: 10px;">
        <small>{now_ist.strftime('%A, %b %d, %Y')}<br>
        {now_ist.strftime('%I:%M:%S %p')} IST</small>
    </div>
    """, unsafe_allow_html=True)

st.info(f"You are currently in **{st.session_state.view}**. Showing team: **{st.session_state.selected_team}**")

is_admin_logged_in = st.session_state.view == 'Admin View' and st.session_state.authenticated
is_employee_view = st.session_state.view == 'Employee View'

# --- View Toggle: Roster vs. Search Results ---
if st.session_state.search_selection != "-- Select Employee --":
    display_employee_details(st.session_state.search_selection)
else:
    if is_employee_view or is_admin_logged_in:
        current_roster_all = st.session_state.rosters.get(roster_key)
        
        # Filter the main roster based on team selection for display
        if current_roster_all is not None:
            roster_for_display = current_roster_all[current_roster_all.index.isin(employees_to_display)]
        else:
            roster_for_display = pd.DataFrame()

        st.markdown("#### Edit Roster")
        if not roster_for_display.empty:
            num_days = calendar.monthrange(selected_year, selected_month_num)[1]
            
            column_config = {
                "Employee": st.column_config.TextColumn("Employee", help="Employee names are managed by the Admin."),
                **{ str(day): st.column_config.SelectboxColumn(
                        label=f"{day} ({calendar.day_abbr[datetime(selected_year, selected_month_num, day).weekday()]})",
                        options=SHIFT_OPTIONS, required=True
                    ) for day in range(1, num_days + 1) }
            }
            
            editor_height = (len(roster_for_display) * 35) + 38
            
            roster_for_editing = roster_for_display.reset_index().rename(columns={'index': 'Employee'})
            
            editor_key = f"roster_editor_{roster_key}_{st.session_state.selected_team}"
            
            edited_df_with_col = st.data_editor(
                roster_for_editing, key=editor_key, column_config=column_config,
                use_container_width=True, height=editor_height, disabled=["Employee"]
            )
            
            edited_df_display = edited_df_with_col.set_index('Employee')

            if not edited_df_display.equals(roster_for_display):
                # Update the main roster dataframe with the changes from the filtered view
                st.session_state.rosters[roster_key].update(edited_df_display)
                save_data()
                st.toast("Roster updated!", icon="✅")
                st.rerun()
        else:
            st.warning("No employees in the selected team. Add employees in the Admin View or select a different team.")
        
        st.markdown("---")
        st.markdown("#### Color-Coded Roster View")
        if not roster_for_display.empty:
            st.dataframe(style_roster(roster_for_display), use_container_width=True)
    else:
        st.warning("Please log in as an Admin to view and edit the roster.")

# --- INSTRUCTIONS ---
st.markdown("---")
with st.expander("ℹ️ How to Use This App"):
    st.markdown("""
    1.  **Dependencies:** Make sure you have `cryptography` installed (`pip install cryptography`).
    2.  **Team Filtering:** Use the 'Filter by Team' dropdown to view specific teams.
    3.  **Admin Functions:** As an Admin, you can manage teams, employees, holidays, and the admin password.
    4.  **Secure Storage:** Your admin password is encrypted in `admin_secret.key`. **Do not share this file or `secret.key`.**
    5.  **Data File:** All other data is saved to `roster_data.json`.
    6.  **Search:** The employee search is filtered by the selected team.
    7.  **Data Propagation:** Changes to employees and rosters are carried forward to future months.
    """)

