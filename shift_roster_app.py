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

if 'data_loaded' not in st.session_state:
    load_data()
    st.session_state.data_loaded = True

SHIFT_OPTIONS = ['General', 'Morning', 'Evening', 'Night', 'Off', 'Holiday']
DEFAULT_SHIFT = 'General'

# --- HELPER FUNCTIONS ---

def get_all_employees():
    """Returns a flat list of uniquely identified employees from all teams."""
    all_employees = []
    for team, members in st.session_state.teams.items():
        for member in members:
            all_employees.append(f"{member} ({team})")
    return sorted(all_employees)

def generate_roster(year, month, employees, holidays):
    """Generates a fresh roster for a given month and year."""
    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)]
    
    if not employees:
        return pd.DataFrame()

    new_roster = pd.DataFrame(index=employees, columns=days).fillna(DEFAULT_SHIFT)

    for day in days:
        current_date = datetime(year, month, int(day)).date()
        if current_date.weekday() >= 5: # Saturday or Sunday
            new_roster[day] = 'Off'
        for holiday in holidays:
            if current_date == holiday['date']:
                new_roster[day] = 'Holiday'
    return new_roster

def generate_roster_from_previous(previous_roster, year, month, employees, holidays):
    """Generates a new roster using the previous month's roster as a template."""
    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)]

    if not employees:
        return pd.DataFrame()

    new_roster = pd.DataFrame(index=employees, columns=days)
    
    common_employees = previous_roster.index.intersection(employees)
    for day in days:
        if day in previous_roster.columns and not common_employees.empty:
            new_roster.loc[common_employees, day] = previous_roster.loc[common_employees, day]

    new_roster.fillna(DEFAULT_SHIFT, inplace=True)

    for day in days:
        current_date = datetime(year, month, int(day)).date()
        if current_date.weekday() >= 5:
            new_roster[day] = 'Off'
        for holiday in holidays:
            if current_date == holiday['date']:
                new_roster[day] = 'Holiday'
    return new_roster

def update_roster_with_new_employees(existing_roster, new_employees, year, month, holidays):
    """Updates an existing roster to reflect changes in the employee list."""
    if not new_employees:
        return pd.DataFrame()

    num_days = calendar.monthrange(year, month)[1]
    days = [str(d) for d in range(1, num_days + 1)]
    
    updated_roster = pd.DataFrame(index=new_employees, columns=days)
    
    for employee in new_employees:
        if employee not in existing_roster.index:
            updated_roster.loc[employee] = DEFAULT_SHIFT
            for day in days:
                current_date = datetime(year, month, int(day)).date()
                if current_date.weekday() >= 5:
                    updated_roster.loc[employee, day] = 'Off'
                for holiday in holidays:
                    if current_date == holiday['date']:
                        updated_roster.loc[employee, day] = 'Holiday'
    
    common_employees = existing_roster.index.intersection(new_employees)
    if not common_employees.empty:
        updated_roster.loc[common_employees, :] = existing_roster.loc[common_employees, :]
        
    return updated_roster

def style_roster(df):
    """Applies color coding to the roster DataFrame for display."""
    def color_cells(val):
        color_map = {
            'General': '#D4EDDA', 'Morning': '#FFF3CD', 'Evening': '#FFF3CD',
            'Night': '#D6D1F5', 'Off': '#F8D7DA', 'Holiday': '#D1ECF1'
        }
        color = color_map.get(val, 'white')
        return f'background-color: {color}; color: black;'
    
    df_to_style = df.copy()
    day_headers = {day: f"{day} ({calendar.day_abbr[datetime(st.session_state.year, st.session_state.month, int(day)).weekday()]})" for day in df_to_style.columns}
    return df_to_style.rename(columns=day_headers).style.apply(lambda s: s.map(color_cells))

def display_employee_details(employee_id):
    """Displays the upcoming schedule for a selected employee."""
    st.header(f"Schedule for {employee_id}")
    today = datetime.now().date()
    
    st.subheader("Upcoming Shifts")
    upcoming_shifts = []
    sorted_roster_keys = sorted(st.session_state.rosters.keys())
    
    for key in sorted_roster_keys:
        roster_year, roster_month = map(int, key.split('-'))
        if roster_year > today.year or (roster_year == today.year and roster_month >= today.month):
            roster_df = st.session_state.rosters[key]
            if employee_id in roster_df.index:
                employee_shifts = roster_df.loc[employee_id]
                for day_str, shift in employee_shifts.items():
                    day = int(day_str)
                    try:
                        shift_date = date(roster_year, roster_month, day)
                        if shift_date >= today:
                            upcoming_shifts.append({"Date": shift_date, "Day": shift_date.strftime("%A"), "Shift": shift})
                    except ValueError:
                        continue
    
    if upcoming_shifts:
        shifts_df = pd.DataFrame(upcoming_shifts).sort_values(by="Date").reset_index(drop=True)
        st.dataframe(shifts_df, use_container_width=True)
    else:
        st.info("No upcoming shifts found.")

    st.subheader("Your Upcoming Holidays")
    employee_holidays = []
    
    for key in sorted_roster_keys:
        roster_year, roster_month = map(int, key.split('-'))
        if roster_year < today.year or (roster_year == today.year and roster_month < today.month):
            continue

        roster_df = st.session_state.rosters[key]
        if employee_id in roster_df.index:
            employee_schedule = roster_df.loc[employee_id]
            for day_str, shift in employee_schedule.items():
                if shift == 'Holiday':
                    day = int(day_str)
                    try:
                        holiday_date = date(roster_year, roster_month, day)
                        if holiday_date >= today:
                            holiday_name = "Holiday" 
                            for h in st.session_state.holidays:
                                if h['date'] == holiday_date:
                                    holiday_name = h['name']
                                    break
                            employee_holidays.append({'Date': holiday_date, 'Holiday Name': holiday_name})
                    except ValueError:
                        continue
    
    if employee_holidays:
        unique_holidays = [dict(t) for t in {tuple(d.items()) for d in employee_holidays}]
        holidays_df = pd.DataFrame(unique_holidays).sort_values(by="Date").reset_index(drop=True)
        st.dataframe(holidays_df, use_container_width=True)
    else:
        st.info("You have no upcoming holidays assigned in the roster.")

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
            
            for key in sorted(st.session_state.rosters.keys()):
                roster_year, roster_month = map(int, key.split('-'))
                roster_date = datetime(roster_year, roster_month, 1).date()

                if roster_date >= change_date:
                    existing_df = st.session_state.rosters[key]
                    st.session_state.rosters[key] = update_roster_with_new_employees(
                        existing_df, all_employees, roster_year, roster_month, st.session_state.holidays
                    )
        
        with st.sidebar.expander("Manage Teams", expanded=False):
            new_team_name = st.text_input("New Team Name", key="new_team_name")
            if st.button("Add Team"):
                if new_team_name and new_team_name not in st.session_state.teams:
                    st.session_state.teams[new_team_name] = []
                    save_data()
                    st.rerun()
            
            team_to_delete = st.selectbox("Select team to delete", options=[""] + list(st.session_state.teams.keys()))
            if st.button("Delete Team"):
                if team_to_delete and not st.session_state.teams[team_to_delete]:
                    del st.session_state.teams[team_to_delete]
                    save_data()
                    st.rerun()
                elif team_to_delete:
                    st.warning("Cannot delete a team with members.")

        with st.sidebar.expander("Manage Employees", expanded=True):
            st.markdown("<h6>Add Employee</h6>", unsafe_allow_html=True)
            new_emp_name = st.text_input("New Employee Name", key="new_emp_name_add")
            team_to_add_to = st.selectbox("Select Team for New Employee", options=list(st.session_state.teams.keys()), key="team_add_select")
            if st.button("Add Employee"):
                if new_emp_name and team_to_add_to and new_emp_name not in st.session_state.teams[team_to_add_to]:
                    st.session_state.teams[team_to_add_to].append(new_emp_name)
                    propagate_employee_changes(selected_year, selected_month_num)
                    save_data()
                    st.rerun()
                elif new_emp_name and new_emp_name in st.session_state.teams.get(team_to_add_to, []):
                    st.warning(f"{new_emp_name} is already in {team_to_add_to}.")

            st.markdown("---")
            st.markdown("<h6>Delete Employee</h6>", unsafe_allow_html=True)
            employee_to_delete = st.selectbox("Select employee to delete", options=[""] + get_all_employees(), key="emp_delete_select")
            if st.button("Delete Employee"):
                if employee_to_delete:
                    try:
                        emp_name, team_name = employee_to_delete.rsplit(' (', 1)
                        team_name = team_name[:-1]

                        if team_name in st.session_state.teams and emp_name in st.session_state.teams[team_name]:
                            st.session_state.teams[team_name].remove(emp_name)
                            propagate_employee_changes(selected_year, selected_month_num)
                            save_data()
                            st.rerun()
                    except ValueError:
                        st.warning("Invalid employee format selected.")

        with st.sidebar.expander("Manage Holidays"):
            holiday_name = st.text_input("Holiday Name", key="holiday_name")
            holiday_date = st.date_input("Holiday Date", key="holiday_date")

            if st.button("Add Holiday"):
                if holiday_name and holiday_date:
                    if any(h['date'] == holiday_date for h in st.session_state.holidays):
                        st.warning("This date is already a holiday.")
                    else:
                        st.session_state.holidays.append({'name': holiday_name, 'date': holiday_date})
                        st.session_state.holidays.sort(key=lambda x: x['date'])

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
                if not new_password:
                    st.warning("Password cannot be empty.")
                elif new_password == confirm_password:
                    save_password(new_password)
                    st.session_state.admin_password = new_password
                    st.sidebar.success("Password changed successfully!")
                else:
                    st.sidebar.error("Passwords do not match.")

        st.sidebar.markdown("---")
        if st.sidebar.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

# --- Shared Controls ---
st.sidebar.markdown("---")
st.sidebar.header("Select Roster Period")
current_year = datetime.now().year
year_options = list(range(current_year - 2, current_year + 3))
saved_year = st.session_state.get('year', current_year)
try:
    year_index = year_options.index(saved_year)
except ValueError:
    year_index = year_options.index(current_year)

month_options = list(range(1, 13))
saved_month = st.session_state.get('month', datetime.now().month)
try:
    month_index = month_options.index(saved_month)  # 1..12
except ValueError:
    month_index = month_options.index(datetime.now().month)

selected_year = st.sidebar.selectbox("Year", year_options, index=year_index, key='year_select')
selected_month_num = st.sidebar.selectbox(
    "Month",
    month_options,
    format_func=lambda x: calendar.month_name[x],
    index=month_index,
    key='month_select'
)

st.session_state.year = selected_year
st.session_state.month = selected_month_num
roster_key = f"{selected_year}-{selected_month_num}"

all_employees_list = get_all_employees()

# --- Roster Generation/Update Logic ---
roster_exists = roster_key in st.session_state.rosters
employees_are_synced = False
if roster_exists:
    # Use set comparison for a more robust check that is order-independent
    employees_are_synced = set(st.session_state.rosters[roster_key].index) == set(all_employees_list)

# Generate or update roster only if it doesn't exist for the period or if employee list has changed
# Generate or update roster only if it doesn't exist or employees truly changed
if not roster_exists:
    prev_month_date = (datetime(selected_year, selected_month_num, 1) - pd.DateOffset(months=1))
    prev_roster_key = f"{prev_month_date.year}-{prev_month_date.month}"
    if prev_roster_key in st.session_state.rosters:
        st.session_state.rosters[roster_key] = generate_roster_from_previous(
            st.session_state.rosters[prev_roster_key], selected_year, selected_month_num, all_employees_list, st.session_state.holidays
        )
    else:
        st.session_state.rosters[roster_key] = generate_roster(
            selected_year, selected_month_num, all_employees_list, st.session_state.holidays
        )
    save_data()



if st.session_state.selected_team == 'All Teams':
    employees_to_display = all_employees_list
else:
    team_members = st.session_state.teams.get(st.session_state.selected_team, [])
    employees_to_display = [f"{member} ({st.session_state.selected_team})" for member in team_members]

st.sidebar.markdown("---")
st.sidebar.header("Search Employee Schedule")
search_options = ["-- Select Employee --"] + employees_to_display
current_search = st.session_state.get('search_selection', "-- Select Employee --")
try:
    search_index = search_options.index(current_search)
except ValueError:
    search_index = 0
selected_employee = st.sidebar.selectbox(
    "Select an employee",
    options=search_options,
    key="search_selection",
    index=search_index
)
st.sidebar.markdown("---")
st.sidebar.header("Holiday Tracker")
if st.session_state.holidays:
    st.sidebar.markdown("**Upcoming Holidays:**")
    for i, holiday in enumerate(list(st.session_state.holidays)):
        if holiday['date'] >= date.today():
            if st.session_state.view == 'Admin View' and st.session_state.authenticated:
                col1, col2 = st.sidebar.columns([3, 1])
                col1.write(f"• {holiday['name']} ({holiday['date'].strftime('%d %b')})")
                if col2.button("Del", key=f"del_holiday_{i}", help="Delete this holiday"):
                    deleted_holiday = st.session_state.holidays.pop(i)
                    deleted_holiday_date = deleted_holiday['date']
                    
                    holiday_roster_key = f"{deleted_holiday_date.year}-{deleted_holiday_date.month}"
                    if holiday_roster_key in st.session_state.rosters:
                        roster_to_update = st.session_state.rosters[holiday_roster_key]
                        day_of_holiday = str(deleted_holiday_date.day)
                        if day_of_holiday in roster_to_update.columns:
                            for emp in roster_to_update.index:
                                if roster_to_update.loc[emp, day_of_holiday] == 'Holiday':
                                    revert_shift = 'Off' if deleted_holiday_date.weekday() >= 5 else DEFAULT_SHIFT
                                    roster_to_update.loc[emp, day_of_holiday] = revert_shift
                    save_data()
                    st.rerun()
            else:
                st.sidebar.write(f"• {holiday['name']} ({holiday['date'].strftime('%d %b')})")
else:
    st.sidebar.info("No holidays added.")


# --- MAIN PAGE ---
col1, col2 = st.columns([2, 1])
with col1:
    if selected_employee == "-- Select Employee --":
        st.title(f"🏢 Shift Roster for {calendar.month_name[selected_month_num]} {selected_year}")
    else:
        st.title("🔎 Search Results")
with col2:
    team_options = ['All Teams'] + list(st.session_state.teams.keys())
    # preserve previously selected team safely (fallback to index 0)
    current_team = st.session_state.get('selected_team', 'All Teams')
    try:
        team_index = team_options.index(current_team)
    except ValueError:
        team_index = 0
    st.selectbox("Filter by Team", options=team_options, key='selected_team', index=team_index)

    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(timezone.utc).astimezone(ist_tz)
    st.markdown(f"""
    <div style="text-align: right; color: grey; margin-top: 10px;">
        <small>{now_ist.strftime('%A, %b %d, %Y')}<br>
        {now_ist.strftime('%I:%M:%S %p')} IST</small>
    </div>
    """, unsafe_allow_html=True)

st.info(f"You are in **{st.session_state.view}**. Showing: **{st.session_state.selected_team}**")

is_admin_logged_in = st.session_state.view == 'Admin View' and st.session_state.authenticated
is_employee_view = st.session_state.view == 'Employee View'

if selected_employee != "-- Select Employee --":
    display_employee_details(selected_employee)
else:
    if is_employee_view or is_admin_logged_in:
        current_roster_all = st.session_state.rosters.get(roster_key)
        
        if current_roster_all is not None:
            roster_for_display = current_roster_all[current_roster_all.index.isin(employees_to_display)].copy()
        else:
            roster_for_display = pd.DataFrame()

        if not roster_for_display.empty:
            st.markdown("#### Edit Roster")
            
            num_days = calendar.monthrange(selected_year, selected_month_num)[1]
            column_config = { "Employee": st.column_config.TextColumn("Employee", disabled=True), **{str(d): st.column_config.SelectboxColumn(f"{d} ({calendar.day_abbr[datetime(selected_year, selected_month_num, d).weekday()]})", options=SHIFT_OPTIONS, required=True) for d in range(1, num_days + 1)}}
            
            editor_key = f"editor_{roster_key}_{st.session_state.selected_team}"

            edited_data = st.data_editor(
                roster_for_display.reset_index().rename(columns={'index': 'Employee'}),
                key=editor_key,
                column_config=column_config, 
                use_container_width=True, 
                disabled=["Employee"]
            )
            
            edited_df_indexed = edited_data.set_index("Employee")

            if not roster_for_display.equals(edited_df_indexed):
                if st.button("Save Changes"):
                    # Replace the DataFrame instead of using .update()
                    st.session_state.rosters[roster_key] = edited_df_indexed.copy()

                    # Persist to disk before rerun
                    save_data()
                    st.toast("Roster updated & saved!", icon="✅")
        
                    # Force re-read from file to ensure persistence
                    load_data()
                    st.rerun()


            st.markdown("---")
            st.markdown("#### Official Color-Coded Roster")
            st.dataframe(style_roster(st.session_state.rosters[roster_key][st.session_state.rosters[roster_key].index.isin(employees_to_display)]), use_container_width=True)


        else:
            st.warning("No employees to display for the selected team.")
    
    else: 
        st.warning("Please log in as an Admin to view and edit the roster.")


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

