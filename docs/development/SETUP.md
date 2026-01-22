## App Setup Guide

### Requirements

- **Python 3.9+**
- **Docker** (installed & running)
- **PostgreSQL** (client, CLI, pgAdmin recommended)
- **Make** (for running Makefile commands)

---

### Setup Steps

1. **Clone the Repository**

```bash
   git clone https://github.com/heisdanielade/api-smart-savings.git
   cd api-smart-savings
```

1. **Install Dependencies**

```bash
pip install -r requirements.txt
```

1. **Configure Environment Variables**

- Copy `.env.example` → `.env` (created by you)
- Create a PostgreSQL database (e.g., `smartsave`)
- Update `.env` with your **database credentials**
- Set one or more test emails under:

```bash
TEST_EMAIL_ACCOUNTS=email1@example.com,email2@example.com
```

- These accounts are used by a **startup script** that seeds test data (e.g., test user accounts).
- Update other values as provided privately by the project manager: ([@heisdanielade](https://github.com/heisdanielade))

1. **Run App Commands**

A docker network is required for the app (Core backend + IMS service) to run. Create it with:

```bash
docker network create smartsave-net
```

Start the app using Docker:

```bash
make build
```

Stop the app using Docker:

```bash
docker network create smartsave-net # Create docker network
make build      # Start app using Docker
make down       # Stop app
make tests      # Run tests
```

More helpful commands are provided in `Makefile` in the project's root directory.

1. **Verification**
   Once the app starts, verify it’s running by visiting:
   **_<http://localhost:3195>_**
