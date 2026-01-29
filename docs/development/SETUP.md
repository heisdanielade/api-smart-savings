## App Setup Guide

### Requirements

- **Python 3.9+**
- **Docker** (installed and running)
- **PostgreSQL** (running instance)
- **Make** (installed to execute Makefile commands)

---

### Setup Steps

#### 1. Clone the Repositories
You will need both the API and the NLP services locally:

```bash
# Clone API repository
git clone https://github.com/heisdanielade/api-smart-savings.git

# Clone NLP repository
git clone https://github.com/ArtemRuzhevych/nlp-savebuddy.git
```

Install dependencies in both directories:

**In the API directory:**
```bash
cd api-smart-savings
pip install -r requirements.txt
```

**In the NLP directory:**
```bash
cd ../nlp-savebuddy
pip install -r requirements.txt
```

#### 2. Configure Environment Variables
Environment variables must be configured in both directories before building.

1. Navigate to each directory (`api-smart-savings/` and `nlp-savebuddy/`).

2. Copy `.env.example` to `.env`.

3. In the API repo, update your database credentials and test emails:

```bash
TEST_EMAIL_ACCOUNTS=email1@example.com,email2@example.com
```
These accounts are used by a **startup script** that seeds test data (e.g., test user accounts). Update other values as provided privately by the project manager: ([@heisdanielade](https://github.com/heisdanielade))

4. Ensure the NLP URL is set to http://localhost:8000.

#### 3. Create Docker Network

The application requires a shared Docker network for the core backend and NLP service which must be initialised from the **API Repository** directory:

```bash
cd api-smart-savings
docker network create smartsave-net
```

#### 4. Run the application (Using Makefile shortcut commands)
**In the API directory:**
```bash
cd api-smart-savings
make build
```

**In the NLP directory:**
```bash
cd ../nlp-savebuddy
make build
```

Common commands:

```bash
make down       # Stop app
make tests      # Run tests
make logs      # View logs (Only in NLP repo)
```

Additional commands are available in `Makefile` at the project's root directory.

#### 5. Verify the setup
Once all containers are healthy, access the services at:

**API Endpoint:** http://localhost:3195

**NLP Service:** http://localhost:8000
