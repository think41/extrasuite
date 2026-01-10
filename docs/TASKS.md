# Fabric Portal - Implementation Tasks

## Task Status Legend
- [ ] Not started
- [x] Completed
- [~] In progress

---

## Phase 1: Project Scaffold

### Task 1.1: Server Scaffold
- [ ] Create server directory structure
- [ ] Initialize uv project with pyproject.toml
- [ ] Configure ruff for linting
- [ ] Configure ty for type checking
- [ ] Create basic FastAPI app structure
- [ ] Add health check endpoints

### Task 1.2: Client Scaffold
- [ ] Create React + TypeScript + Vite project
- [ ] Configure TailwindCSS
- [ ] Set up ESLint and Prettier
- [ ] Configure Vite for port 5174
- [ ] Create basic App component

### Task 1.3: Docker Setup
- [ ] Create multi-stage Dockerfile
- [ ] Create docker-compose.yml for local development
- [ ] Test Docker build

---

## Phase 2: Core API Implementation

### Task 2.1: Google OAuth Integration
- [ ] Add Google OAuth dependencies
- [ ] Implement OAuth initiation endpoint
- [ ] Implement OAuth callback handler
- [ ] Implement user info endpoint
- [ ] Implement logout endpoint
- [ ] Add session management

### Task 2.2: Service Account Creation API
- [ ] Add Google Cloud IAM dependencies
- [ ] Implement magic token generation
- [ ] Implement service account creation
- [ ] Implement JSON download endpoint (one-time use)
- [ ] Store service account email in metadata
- [ ] Implement status check endpoint

---

## Phase 3: Frontend Implementation

### Task 3.1: Authentication UI
- [ ] Create login page with Google sign-in button
- [ ] Implement OAuth redirect handling
- [ ] Add user session state management
- [ ] Create logout functionality

### Task 3.2: Main Portal Page
- [ ] Design main dashboard layout
- [ ] Show user info and EA status
- [ ] Display OS-specific shell commands
- [ ] Show EA email once created

### Task 3.3: Instructions & Help
- [ ] Create "How It Works" section
- [ ] Add FAQ section
- [ ] Add troubleshooting guide
- [ ] Create help documentation

---

## Phase 4: Integration & Polish

### Task 4.1: Frontend-Backend Integration
- [ ] Connect login flow end-to-end
- [ ] Connect service account creation flow
- [ ] Add loading states and error handling

### Task 4.2: Testing
- [ ] Test all API endpoints with curl
- [ ] Test frontend flows
- [ ] Test Docker container

### Task 4.3: Documentation
- [ ] Create comprehensive README.md
- [ ] Document all environment variables
- [ ] Add deployment instructions for Cloud Run

---

## Progress Log

### Session 1 - Initial Setup
- Created project plan and task breakdown
- (Tasks will be logged here as completed)
