# Authentication API Explanation

This document describes only the authentication part of CSCM.

## Overview

The authentication system uses:

- A local SQLite database file: `auth.db`
- A local user account with `username` and hashed `password`
- TOTP multi-factor authentication with a 6-digit one-time code
- JWT bearer tokens for authenticated API access

The authentication flow is:

1. Open the application.
2. Check whether a user already exists.
3. If no user exists yet, create the first administrator account.
4. Save the TOTP secret in an authenticator app by scanning the QR code or entering the manual secret.
5. Log in with username, password, and current TOTP code.
6. Receive a JWT token.
7. Send the JWT token in the `Authorization` header for protected API calls.

## Important Concepts

### Local auth database

Authentication data is not stored in the PostgreSQL server database.
It is stored locally in `auth.db`.

This database stores:

- users
- password hashes
- TOTP secrets
- JWT signing configuration

### Password handling

Passwords are not stored as plain text.
They are hashed before storage.

### Multi-factor authentication

Login requires:

- username
- password
- one-time TOTP code

The TOTP code comes from an authenticator app such as:

- Google Authenticator
- Microsoft Authenticator
- Authy
- 1Password

### JWT usage

After a successful login, the backend returns a JWT token.
Use it in this header:

```http
Authorization: Bearer <jwt_token>
```

All protected endpoints must receive this header.

## Auth Endpoints

## 1. GET /

### Purpose

Serves the authentication page.

### Authentication required

No.

### Request

```http
GET /
```

### Response

Returns the HTML page for setup/login.

### Frontend use

Use this as the entry page for the authentication UI.

---

## 2. GET /api/auth/status

### Purpose

Returns the current authentication bootstrap state.
This endpoint tells the frontend:

- whether the application still needs first-time setup
- whether the provided JWT is valid
- which user is authenticated, if any

### Authentication required

No, but if a bearer token is sent, it will be checked.

### Request

```http
GET /api/auth/status
```

Optional header:

```http
Authorization: Bearer <jwt_token>
```

### Response when no user exists yet

```json
{
  "setup_required": true,
  "authenticated": false,
  "user": null
}
```

### Response when a user exists and no valid token is provided

```json
{
  "setup_required": false,
  "authenticated": false,
  "user": null
}
```

### Response when a valid token is provided

```json
{
  "setup_required": false,
  "authenticated": true,
  "user": {
    "id": 1,
    "username": "admin"
  }
}
```

### Frontend use

Call this first when the frontend loads.

Use the result like this:

- if `setup_required` is `true`, show the setup form
- if `setup_required` is `false`, show the login form
- if `authenticated` is `true`, restore logged-in UI state

---

## 3. POST /api/auth/setup

### Purpose

Creates the first local administrator account and returns TOTP setup data.

This endpoint is only for first-time setup.
After the first user exists, it can no longer be used.

### Authentication required

No.

### Request

```http
POST /api/auth/setup
Content-Type: application/json
```

Body:

```json
{
  "username": "admin",
  "password": "very-strong-password"
}
```

### Required fields

- `username`: string
- `password`: string

### Validation rules

- username must not be empty
- username must be at least 3 characters long
- password must be at least 12 characters long
- setup only works if no user exists yet

### Success response

Status: `201 Created`

```json
{
  "success": true,
  "message": "Initial account created. Scan the QR code and then sign in with your one-time password.",
  "totp_secret": "BASE32SECRET",
  "totp_uri": "otpauth://totp/CSCM%20Tool:admin?...",
  "qr_code_data_uri": "data:image/svg+xml;base64,..."
}
```

### Returned fields

- `success`: boolean
- `message`: user-facing success message
- `totp_secret`: manual TOTP secret for authenticator app entry
- `totp_uri`: provisioning URI for TOTP setup
- `qr_code_data_uri`: QR code image as a data URI for direct rendering in the browser

### Error response: invalid input

Status: `400 Bad Request`

Example:

```json
{
  "error": "Password must be at least 12 characters long"
}
```

### Error response: setup already completed

Status: `409 Conflict`

```json
{
  "error": "Initial setup has already been completed"
}
```

### Frontend use

After a successful response:

- display the QR code using `qr_code_data_uri`
- display the manual secret using `totp_secret`
- optionally display the provisioning URI
- instruct the user to add the TOTP entry to an authenticator app
- after setup, move the user to the login form

---

## 4. POST /api/auth/login

### Purpose

Authenticates a user with username, password, and TOTP code.
Returns a JWT token if login succeeds.

### Authentication required

No.

### Request

```http
POST /api/auth/login
Content-Type: application/json
```

Body:

```json
{
  "username": "admin",
  "password": "very-strong-password",
  "otp": "123456"
}
```

### Required fields

- `username`: string
- `password`: string
- `otp`: string

### Success response

Status: `200 OK`

```json
{
  "success": true,
  "token": "jwt-token-here",
  "token_type": "Bearer",
  "expires_at": 1780250000,
  "user": {
    "id": 1,
    "username": "admin"
  }
}
```

### Returned fields

- `success`: boolean
- `token`: JWT token
- `token_type`: always `Bearer`
- `expires_at`: unix timestamp when token expires
- `user.id`: authenticated user id
- `user.username`: authenticated username

### Error response: setup not completed yet

Status: `403 Forbidden`

```json
{
  "error": "Setup required",
  "setup_required": true
}
```

### Error response: missing fields

Status: `400 Bad Request`

```json
{
  "error": "'username', 'password', and 'otp' are required"
}
```

### Error response: invalid credentials or invalid TOTP

Status: `401 Unauthorized`

```json
{
  "error": "Invalid username, password, or one-time password"
}
```

### Frontend use

After successful login:

- save `token`
- save `user`
- send the token as bearer auth for protected API calls
- use `expires_at` to know session expiry time if needed

---

## 5. GET /api/auth/me

### Purpose

Checks the current JWT and returns the authenticated user.

### Authentication required

Yes.

### Request

```http
GET /api/auth/me
Authorization: Bearer <jwt_token>
```

### Success response

Status: `200 OK`

```json
{
  "authenticated": true,
  "user": {
    "id": 1,
    "username": "admin"
  }
}
```

### Error response: no user exists yet

Status: `403 Forbidden`

```json
{
  "error": "Setup required",
  "setup_required": true
}
```

### Error response: missing or invalid token

Status: `401 Unauthorized`

```json
{
  "error": "Unauthorized"
}
```

### Frontend use

Use this endpoint when you want to validate the current session explicitly.

---

## Protected Authentication Behavior

All protected endpoints use JWT authentication.

### Required header

```http
Authorization: Bearer <jwt_token>
```

### If setup has not been completed

Protected endpoints return:

Status: `403 Forbidden`

```json
{
  "error": "Setup required",
  "setup_required": true
}
```

### If token is missing or invalid

Protected endpoints return:

Status: `401 Unauthorized`

```json
{
  "error": "Unauthorized"
}
```

## Recommended Frontend Usage Flow

## First launch flow

1. Open the app.
2. Call `GET /api/auth/status`.
3. If `setup_required` is `true`, show the setup form.
4. Submit `POST /api/auth/setup`.
5. Display QR code and/or manual secret.
6. Ask the user to configure an authenticator app.
7. Show the login form.
8. Submit `POST /api/auth/login`.
9. Save the returned JWT.

## Normal login flow

1. Open the app.
2. Call `GET /api/auth/status`.
3. If setup is already completed, show the login form.
4. Submit `POST /api/auth/login` with username, password, and TOTP.
5. Save the JWT token.
6. Use the JWT for all protected endpoints.

## Session restore flow

1. Load JWT from storage.
2. Send it to `GET /api/auth/status` or `GET /api/auth/me`.
3. If valid, keep the user logged in.
4. If invalid, clear the token and return to login.

## Storage Recommendations for Frontend

At the moment, the existing template stores the JWT in browser local storage.

Current key:

```text
cscm_jwt
```

If your frontend is separate, you can store:

- JWT token
- minimal user info
- token expiry timestamp

## What the frontend should send

For login and setup:

- JSON body
- `Content-Type: application/json`

For protected auth checks:

- `Authorization: Bearer <jwt_token>`

## What is not implemented yet

This authentication system currently does not provide:

- logout endpoint
- refresh token endpoint
- password reset endpoint
- create additional users endpoint
- delete user endpoint
- rotate TOTP secret endpoint
- disable MFA endpoint

Logout is currently frontend-only by deleting the stored JWT.

## Summary

Authentication in CSCM works like this:

- first boot requires initial administrator creation
- setup returns QR code and TOTP secret
- login requires username, password, and TOTP code
- successful login returns a JWT
- protected routes require `Authorization: Bearer <token>`
- auth data is stored locally in `auth.db`
