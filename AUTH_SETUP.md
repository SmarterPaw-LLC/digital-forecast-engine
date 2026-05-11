# Auth Setup — One-Time Steps in Supabase Dashboard

You'll do this once. After it's done, the dashboard requires login and Google sign-in works.

---

## Step 1 — Run the SQL migration

1. Open https://supabase.com/dashboard → your `yjcnuyoaemlipvuinptp` project
2. Left sidebar → **SQL Editor** → **New query**
3. Open `supabase_auth_setup.sql` in this folder, copy the whole contents, paste into the SQL Editor
4. Click **Run**

You should see "Success. No rows returned." at the bottom. This creates `user_profiles`, `audit_log`, and locks down every existing table behind authentication.

---

## Step 2 — Create your first admin account

The dashboard won't let anyone in until at least one user exists.

1. Supabase dashboard → **Authentication** → **Users** → **Add user** → **Create new user**
2. Email: your work email
3. Password: pick a strong one (this is your dashboard login)
4. Check **Auto Confirm User** (so you don't need to click an email link)
5. Click **Create user**

That email/password is now your login. The SQL migration's trigger auto-created your `user_profiles` row as `admin`.

---

## Step 3 — Configure Google Sign-In

This enables the "Sign in with Google" button on the login page.

### 3a. Create a Google OAuth client

1. Open https://console.cloud.google.com/
2. If you don't have a project, create one (name it "SmarterPaw Dashboard" or similar)
3. Left sidebar → **APIs & Services** → **OAuth consent screen**
   - User type: **External** (unless you have Google Workspace)
   - App name: "SmarterPaw Forecast"
   - User support email: yours
   - Developer contact: yours
   - Click **Save and Continue** through the other screens; you can skip scopes
4. Left sidebar → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Web application**
   - Name: "SmarterPaw Forecast"
   - **Authorized JavaScript origins** — add both:
     - `https://smarterpaw-llc.github.io`
     - `http://localhost` (for local testing)
   - **Authorized redirect URIs** — add this exact URL (Supabase needs it):
     - `https://yjcnuyoaemlipvuinptp.supabase.co/auth/v1/callback`
   - Click **Create**
5. Copy the **Client ID** and **Client secret** that appear

### 3b. Configure the Google provider in Supabase

1. Supabase dashboard → **Authentication** → **Providers**
2. Find **Google**, click to expand
3. Toggle **Enabled** on
4. Paste the **Client ID** from step 3a
5. Paste the **Client Secret** from step 3a
6. Leave "Skip nonce check" unchecked
7. Click **Save**

### 3c. Set the Site URL (so redirects come back correctly)

1. Supabase dashboard → **Authentication** → **URL Configuration**
2. **Site URL**: `https://smarterpaw-llc.github.io/digital-forecast-engine/`
3. **Redirect URLs** (add each as a separate entry, click `Add URL` after each):
   - `https://smarterpaw-llc.github.io/digital-forecast-engine/`
   - `https://smarterpaw-llc.github.io/digital-forecast-engine/**`
4. Click **Save changes**

---

## Step 4 — Inviting other users

After deploying v4.59+:
1. Open the live dashboard, log in with your admin account
2. Go to **Settings** → **Users** section
3. Enter the new user's email, click **Invite**
4. Supabase emails them a "set your password" link
5. They sign up via that link → on first login, the trigger auto-creates their `user_profiles` row as `admin`
6. They can also use Google sign-in if their email matches what you invited (Supabase links the accounts)

Removing a user: in Supabase → **Authentication** → **Users** → click the user → **Delete user**. The `user_profiles` row deletes via cascade.

---

## Step 5 — Verify

After deploying the dashboard code:

- Visit the live site. You should see a login screen, **not** the old password input.
- Log in with your email/password from Step 2 → should land in the dashboard.
- Open Settings → **Audit Log** section — should show your login row.
- Click **Sign in with Google** in an incognito window → should redirect to Google → back to dashboard.

If Google sign-in errors with "redirect_uri_mismatch," recheck Step 3a/3c — the URLs must match exactly.

---

## Future maintenance

- **Reset a user's password**: Supabase → Authentication → Users → click user → **Send password recovery**.
- **View audit log**: Settings tab in the dashboard, or directly: `select * from audit_log order by ts desc limit 100;` in SQL Editor.
- **Add a new role tier** (e.g. read-only viewer): change the `role` column on their `user_profiles` row, then narrow the RLS policies on individual tables.
