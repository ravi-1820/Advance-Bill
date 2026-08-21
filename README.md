# 🧾 Advance Billing System with QR

A modern, full-stack **Enterprise Advance Billing & Distributor POS System** built with **Django**, **HTML5**, **CSS3**, and **JavaScript**. Featuring instant dynamic QR code billing, inventory ledgers, role-based authentication, temporary DB-backed OTP password resets, and a sleek dark/light design system.

---

## ✨ Features

- **🚀 Instant Dynamic QR Billing**: Generate dynamic payment QR codes with automatic payload encoding.
- **🛒 Distributor POS Workspace**: Manage stock ledgers, real-time inventory sync, daily settlement summaries, and customer invoices.
- **⚙️ Master Admin Control Center**: Monitor system revenue, active distributors, credit limits, security signature keys, and tax compliance audit logs.
- **🛡️ Role-Based Authentication**: Secure portal for both **Distributor** and **Administrator** access.
- **📲 DB-Backed 6-Digit OTP**: Temporary database-stored 6-digit OTP generation with 5-minute expiry validation for secure password resets.
- **📝 Distributor Self-Registration**: Instant distributor onboarding generating unique `DIST-XXXXX` IDs.
- **🌙 Modern UI & Theme Switcher**: Glassmorphism design system supporting live Dark and Light modes.

---

## 🛠️ Project Setup & Installation

Follow these steps to set up and run the project locally on your machine:

### 1. Clone Repository
```bash
git clone https://github.com/ravi-1820/Advance-Bill.git
cd Advance-Bill
```

### 2. Set Up Virtual Environment
On Windows:
```cmd
python -m venv .venv
.venv\Scripts\activate
```
On macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install django
```

### 4. Database Setup & Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Seed Default Users
Run the custom management command to initialize default Admin and Distributor accounts:
```bash
python manage.py create_seed_users
```

### 6. Start Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```

Open **`http://127.0.0.1:8000/`** in your browser to access the portal.

---

## 🔑 Default Login Credentials

Use the pre-seeded development credentials to access the system:

### 🛡️ Admin Portal Credentials
- **Email / Username:** `admin@advancebilling.com` (or `admin`)
- **Password:** `admin123`

### 🛒 Distributor POS Credentials
- **Distributor ID:** `DIST-77492`
- **Mobile Number:** `94095369850`
- **Password:** `distributor123`

---

## 📁 Project Structure

```text
Advance-Bill/
├── advance_bill/          # Core Django project settings & URL routing
├── billing/               # Main billing application
│   ├── management/        # Custom seed management commands
│   ├── migrations/        # Database migrations
│   ├── static/            # CSS & JS assets
│   ├── templates/         # HTML portal & dashboard templates
│   ├── admin.py           # Admin panel model registrations
│   ├── models.py          # User & OTP database models
│   ├── urls.py            # App route patterns
│   └── views.py           # Authentication & dashboard view logic
├── db.sqlite3             # SQLite local database
├── manage.py              # Django CLI utility
└── README.md              # Documentation
```

---

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
