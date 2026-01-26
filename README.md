# 💰 SmartSave - GDPR-Compliant Savings App (EU/Poland)

![API Version](https://img.shields.io/badge/API%20version-v1.0.0-blue.svg)
[![FastAPI](https://img.shields.io/badge/FastAPI-009485.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=Pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Pytest](https://img.shields.io/badge/Pytest-fff?logo=pytest&logoColor=000)](https://docs.pytest.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=fff)](https://www.docker.com/)
[![Postgres](https://img.shields.io/badge/Postgres-%23316192.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-%23DD0031.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Bash](https://img.shields.io/badge/Bash-4EAA25?logo=gnubash&logoColor=fff)](https://www.gnu.org/software/bash/)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)

## Overview

**SmartSave** is a GDPR-compliant smart savings application designed for users in the EU, focusing on transparency, collaboration, and security.  
It combines traditional savings with NLP-powered automated savings via the **SaveBuddy AI assistant**, allowing users to manage personal and group savings easily, while keeping their data private and secure.  

## Contributors

| Developer | GitHub Username | Responsibilities                                                                                                                                       |
|------------|-----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| Daniel Adediran | [@heisdanielade](https://github.com/heisdanielade) | **Core Backend, DevOps & Frontend** - repo management, authentication, profile & wallet management, savings, GDPR, notifications, CI/CD, SaveBuddy AI & frontend dev |
| Danylo Samedov | [@DanSamedov](https://github.com/DanSamedov) | **Core Backend & Frontend** - authentication, profile & wallet management, transactions, savings, testing, SaveBuddy AI & frontend dev                 |
| Artem Ruzhevych | [@ArtemRuzhevych](https://github.com/ArtemRuzhevych) | **AI & Backend integrations** - SaveBuddy AI system, logging, notifications, user analytics, GDPR, API metrics, research and testing                                   |

## Table of Contents
  
1. [Features](#features)  
2. [Snapshots](#snapshots)  
3. [Architecture](#architecture)  
4. [Authentication](#authentication)  
5. [Authorization](#authorization)  
6. [GDPR Compliance](#gdpr-compliance)  
7. [Core Savings](#core-savings)  
8. [Technologies & Design Decisions](#technologies--design-decisions)
9. [Future Improvements](#future-improvements)  
10. [Closing Note](#closing-note)

## Features

- Individual and group savings management  
- AI savings assistant (**SaveBuddy**) for automation, requires user consent  
- GDPR-compliant data handling and user privacy management  
- Email-based OTP verification and secure login (JWT & OAuth)
- Detailed requests logging with hashed IPs  
- Rate limiting, and background email notifications  
- CI/CD integration for automated deployments  
- Redis caching and PostgreSQL indexing for performance  
- Modular and scalable monorepo architecture  

---

## Architecture

### Monorepo & Modular Design

SmartSave uses a **modular architecture** within a **monorepo** setup.  
Each feature lives in its own module under the `modules/` directory, designed for separation of concerns and ease of scaling.

**Modules:**

- `auth` — authentication and authorization logic  
- `gdpr` — GDPR compliance and user data management  
- `user` — user profile and preferences  
- `rbac` — admin actions and access control  
- `wallet` — wallet creation and balance management  
- `savings` — individual and group savings  
- `notifications` — email-based user notifications  
- `shared` — reusable schemas and utilities

Each module contains:

```yaml
  repository.py # Database access layer
  models.py # Database models (except Auth module)
  schemas.py # Pydantic schemas
  service.py # Business logic
  helpers.py # Utility functions (optional)
```

### API & Infrastructure Highlights

- **Versioning:** `/v1/...` URL structure for all endpoints  
- **Docs:** Swagger & ReDoc available at `/v1/docs` (protected with Basic Auth)  
- **Rate Limiting:** `Per-minute/hour` restrictions per IP  
- **Redis:** Used for `caching` and fast data retrieval with reasonable TTLs + manual cache invalidation
- **Logging:** Structured `JSON logs` per request, with hashed IP addresses  
- **Makefile:** Common commands for Docker, Alembic, and Pytest  
- **Scripts:** Dev and prod startup scripts in `scripts/`  
- **Database:** PostgreSQL + Alembic for `DB migrations`  
- **CI/CD:** GitHub Actions workflows (`ci.yml`, `cd.yml`)  
- **Environment:** `.env.example` provided for configuration variables  

**Backend System Flow:**  

```bash
  Middleware → Router → Service → Repository → Database
```

---

## Authentication

SmartSave uses a secure, stateless authentication system built with **JWT (JSON Web Tokens)** and **Email-based OTP (One-Time Password)** verification.

- **Registration**: Secure onboarding with 6-digit OTP verification.
- **Security**: Account locking after failed attempts and real-time login notifications.
- **Global Logout**: Immediate token invalidation via versioning.

👉 **[Read the full Authentication breakdown here](docs/features/AUTHENTICATION.md)**

---

## Authorization

Permissions are managed through a fine-grained **Role-Based Access Control (RBAC)** system, ensuring data integrity and user privacy.

- **Roles**: Distinct permissions for `USER`, `ADMIN`, and `SUPER_ADMIN`.
- **Integrity**: Financial data (wallets and transactions) is immutable and append-only.
- **RBAC**: Guarded endpoints using FastAPI dependency injection.

👉 **[Read the full Authorization breakdown here](docs/features/AUTHORIZATION.md)**

---

## GDPR Compliance

Privacy is a first-class citizen in SmartSave. The application is built around the core principles of the **General Data Protection Regulation (GDPR)**.

- **Data Rights**: Full support for Right to Access (Encrypted PDF exports) and Right to Forget (Anonymization).
- **Log Privacy**: Irreversible hashing of IP addresses in all system logs.
- **Consent**: AI-powered features like **SaveBuddy** require explicit user consent.

👉 **[Read the full GDPR Compliance breakdown here](docs/features/GDPR.md)**

---

## Caching with Redis

To improve performance and reduce database load, we implemented **Redis caching** for frequently accessed endpoints, optimizing both latency and scalability.

👉 **[Read the full Caching breakdown here](docs/features/CACHING.md)**

---

## Core Savings

SmartSave provides a comprehensive system for individual and collaborative savings, backed by a secure virtual wallet.

- **Individual Goals**: Set personal targets and track progress.
- **Group Squads**: Save together with shared goals and real-time history.
- **Wallet Hub**: Centralized balance management with multi-currency support.

👉 **[Read the full Savings & Wallet breakdown here](docs/features/SAVINGS.md)**

---

## Technologies & Design Decisions

| Technology | Purpose | Design Relation |
|-------------|----------|-----------------|
| **FastAPI** | High-performance backend & auto-generated docs | Enables clear dependency injection and modular design |
| **Pydantic** | Data validation and serialization | Supports DRY and type-safe schema sharing |
| **SQLModel + SQLAlchemy** | ORMs for PostgreSQL | Enforces consistent data access layer (Repository pattern) |
| **Alembic** | Database migrations | Streamlined schema versioning |
| **Slow-api** | Rate-limiting | For security and simplified implementation |
| **Redis** | Caching | Optimizes performance and scalability |
| **Docker** | Containerization | Simplifies setup and deployment |
| **Pytest** | Automated testing | Ensures reliability and regression safety |
| **GitHub Actions** | CI/CD pipeline | Automates testing and deployment |
| **React** | Frontend | User interface and experience |
| **Tailwind CSS** | Styling | Responsive and modern design |
| **Vite** | Build tool | Fast and modern frontend development |

### Design Principles/Patterns in Action

- **SOLID:** Dependency Injection in routers promotes modular and testable code.  
- **DRY:** Shared helpers and reusable service methods minimize duplication.  
- **Separation of Concerns:** Clear flow: *Middleware → Router → Service → Repository*.  
- **Extensibility:** Notification service follows the **ABC pattern**, allowing easy integration of SMS or push services in the future.
- **Factory + Registry Pattern:** The email notification system uses a combination of design patterns:
  - **Factory Pattern** (`EmailProviderFactory`): Dynamically selects the email provider (SMTP or Resend) based on configuration, enabling easy switching between providers without code changes.
  - **Registry Pattern** (`EMAIL_TEMPLATES`): Maps notification types to their corresponding templates, subjects, and context models in a centralized dictionary, making it simple to add new notification types.
  - **Strategy Pattern** (`EmailProvider` ABC): Defines a common interface for different email providers, allowing interchangeable implementations while maintaining consistent behavior.
  - This architecture ensures the notification system is flexible, maintainable, and easily extensible for new providers or notification types.

---

## Snapshots

Few snapshots of the frontend screens, backend endpoints, email templates & API responses.

### Frontend View (Desktop)

| Description       | Preview                                                                |
|-------------------|------------------------------------------------------------------------|
| **Landing Page**  | ![Landing Page](assets/images/frontend/landing.png)                    |
| **Login Page**    | ![Login Page](./assets/images/frontend/login.png)                      |
| **User Dashboard** | ![User Dashboard](assets/images/frontend/user_dashboard.png)           |
| **User Profile**  | ![User Profile](assets/images/frontend/user_profile.png)               |
| **Transactions**  | ![Transactions](assets/images/frontend/transactions.png)               |
| **Group Details** | ![Group Details](assets/images/frontend/group_details.png)             |
| **Group Members** | ![Group Members](assets/images/frontend/group_members.png)             |
| **Group Chat**    | ![Group Chat](assets/images/frontend/group_chat.png)                   |
| **Withdraw from Group** | ![Withdraw from Group](assets/images/frontend/withdraw_from_group.png) |
| **Data Report Request** | ![Data Report Request](./assets/images/frontend/gdpr_data_request.png) |

### Frontend View (Mobile)

| Description       | Preview                                                                |
|-------------------|------------------------------------------------------------------------|
| **Mobile Dashboard** | ![Mobile Dashboard](assets/images/frontend/mobile_user_dashboard.png) |
| **Mobile Groups**    | ![Mobile Groups](assets/images/frontend/mobile_groups.png)            |
| **Mobile Chat**      | ![Mobile Chat](assets/images/frontend/mobile_group_chat.png)          |
| **Mobile Transactions** | ![Mobile Transactions](assets/images/frontend/mobile_transactions.png) |

### API Endpoints (Swagger)

| Description               | Preview                                                                              |
|---------------------------|--------------------------------------------------------------------------------------|
| **Authentication**        | ![Authentication Endpoints](./assets/images/endpoints/auth.png)                      |
| **Account & GDPR**        | ![Account Management & GDPR Endpoints](./assets/images/endpoints/account_gdpr.png) |
| **Wallet & Transactions** | ![Wallet & Transactions Endpoints](./assets/images/endpoints/wallet.png)             |
| **Admin & Groups**        | ![Admin & Groups Endpoints](./assets/images/endpoints/admin_groups.png)            |

### Email Templates

| Description           | Preview                                                              |
|-----------------------|----------------------------------------------------------------------|
| **Login Notification** | ![Login Notification](./assets/images/emails/login_notification.png) |
| **Reset Password**    | ![Reset Password](./assets/images/emails/reset_password.png)         |
| **GDPR Data Export**  | ![GDPR Data Export](./assets/images/emails/gdpr_data_export.png)     |
| **Wallet Deposit**    | ![Wallet Deposit](./assets/images/emails/wallet_deposit.png)         |

### API Responses

| Description             | Preview                                                                   |
|-------------------------|---------------------------------------------------------------------------|
| **Wallet Deposit**      | ![Wallet Deposit](./assets/images/responses/wallet_deposit.png)           |
| **Wallet Transactions** | ![Wallet Transactions](./assets/images/responses/wallet_transactions.png) |

---

## Future Improvements

- Introduce **referral system** for user growth.  
- Split modules into **dedicated microservices** for better scalability.  
- Integrate **real banking APIs** for live savings and transactions.  
- Add **SMSNotificationService** and **push notifications**.  
- Expand **SaveBuddy AI** to provide personalized financial recommendations.

---

## Closing Note

SmartSave was initially designed as a final-year project by 3 students from the `University of Zielona Gora - Computer Science & Econometrics` but advanced to a production-grade system. It's not just a financial tool but a **trustworthy digital companion** for responsible saving.  
Built with transparency, collaboration, and user privacy at its core; this project is a foundation for modern, ethical financial technology.

**Thank you for checking out SmartSave! 💚**

## License

This project is licensed under a **STRICT PROPRIETARY LICENSE**.
**Strictly prohibited:**

- Automated scraping or data mining.
- AI training, fine-tuning, or evaluation using this codebase.
- Redistribution without explicit written permission.

See the [LICENSE](LICENSE) file for full details.
