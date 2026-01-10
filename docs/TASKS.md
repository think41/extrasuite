# Fabric Portal - Implementation Tasks

## Task Status Legend
- [ ] Not started
- [x] Completed
- [~] In progress

---

## Phase 1: Project Scaffold

### Task 1.1: Server Scaffold
- [x] Create server directory structure
- [x] Initialize uv project with pyproject.toml
- [x] Configure ruff for linting
- [x] Create basic FastAPI app structure
- [x] Add health check endpoints

### Task 1.2: Client Scaffold
- [x] Create React + TypeScript + Vite project
- [x] Configure TailwindCSS v4
- [x] Set up ESLint
- [x] Configure Vite for port 5174
- [x] Create App component with full portal UI

### Task 1.3: Docker Setup
- [x] Create multi-stage Dockerfile
- [x] Create docker-compose.yml for local development
- [ ] Test Docker build (Docker not available on dev machine)

---

## Phase 2: Core API Implementation

### Task 2.1: Google OAuth Integration
- [x] Add Google OAuth dependencies (google-auth-oauthlib)
- [x] Implement OAuth initiation endpoint (/api/auth/google)
- [x] Implement OAuth callback handler (/api/auth/callback)
- [x] Implement user info endpoint (/api/auth/me)
- [x] Implement logout endpoint (/api/auth/logout)
- [x] Add session management with signed cookies

### Task 2.2: Service Account Creation API
- [x] Add Google Cloud IAM dependencies (google-api-python-client)
- [x] Implement magic token generation
- [x] Implement service account creation
- [x] Implement JSON download endpoint (one-time use)
- [x] Store service account email in metadata
- [x] Implement status check endpoint

---

## Phase 3: Frontend Implementation

### Task 3.1: Authentication UI
- [x] Create login page with Google sign-in button
- [x] Implement OAuth redirect handling
- [x] Add user session state management
- [x] Create logout functionality

### Task 3.2: Main Portal Page
- [x] Design main dashboard layout
- [x] Show user info and EA status
- [x] Display OS-specific shell commands (macOS/Linux/Windows)
- [x] Show EA email once created
- [x] Add copy-to-clipboard functionality

### Task 3.3: Instructions & Help
- [x] Create "How It Works" section
- [x] Add FAQ section
- [x] Create help documentation

---

## Phase 4: Integration & Polish

### Task 4.1: Frontend-Backend Integration
- [x] Connect login flow end-to-end
- [x] Connect service account creation flow
- [x] Add loading states and error handling

### Task 4.2: Testing
- [x] Test all API endpoints with curl (health, auth)
- [x] Client builds successfully
- [ ] Full end-to-end testing (requires Google OAuth credentials)

### Task 4.3: Documentation
- [x] Create comprehensive README.md
- [x] Document all environment variables
- [x] Add deployment instructions for Cloud Run

---

## Progress Log

### Session 1 - Complete Implementation
- Created project plan and task breakdown
- Implemented FastAPI server with:
  - Health check endpoints
  - Google OAuth authentication
  - Service account creation with magic tokens
  - Session management with signed cookies
- Implemented React client with:
  - TailwindCSS v4 styling
  - Full portal UI with login and dashboard
  - OS-specific command display
  - FAQ and instructions
- Created Docker configuration:
  - Multi-stage Dockerfile combining client and server
  - docker-compose.yml for local development
- Created comprehensive README documentation

### Remaining Items
- [ ] Test Docker build
- [ ] Full end-to-end testing with Google OAuth credentials
- [ ] Deploy to Google Cloud Run
