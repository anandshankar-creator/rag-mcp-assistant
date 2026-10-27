import sys
import time
import json
import functools
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print = functools.partial(print, flush=True)

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

from app.config import settings
from app.auth import generate_password_reset_token, reset_password_with_token

def verify_live_auth_flow():
    results = {}
    print("=== LIVE PLAYWRIGHT AUTHENTICATION FLOW VERIFICATION ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        # ---------------------------------------------------------
        # Step 1: Unauthenticated Access Check
        # ---------------------------------------------------------
        print("\n1. Navigating to http://127.0.0.1:8501 (Unauthenticated)...")
        page.goto("http://127.0.0.1:8501", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Confirm Login View is rendered
        login_header = page.locator("text=Administrator Sign In")
        assert login_header.is_visible(), "Administrator Sign In header not visible!"

        # Confirm protected resources are NOT visible
        chat_input = page.locator("[data-testid='stChatInput']")
        chat_visible = chat_input.is_visible()
        print(f"Chat input visible unauthenticated: {chat_visible} (Expected: False)")
        assert not chat_visible, "Security violation: Chat input visible to unauthenticated user!"

        sidebar_docs = page.locator("text=Stored Documents")
        sidebar_docs_visible = sidebar_docs.is_visible()
        print(f"Stored Documents visible unauthenticated: {sidebar_docs_visible} (Expected: False)")
        assert not sidebar_docs_visible, "Security violation: Stored documents visible to unauthenticated user!"

        shot08 = str(SCREENSHOTS_DIR / "08_login_screen.png")
        page.screenshot(path=shot08, full_page=False)
        results["screenshot_08_login"] = shot08
        print(f"Saved Screenshot 08: {shot08}")

        # ---------------------------------------------------------
        # Step 2: Invalid Login Attempt
        # ---------------------------------------------------------
        print("\n2. Submitting invalid credentials...")
        email_field = page.locator("input[aria-label='Administrator Email']")
        pwd_field = page.locator("input[aria-label='Password']")

        email_field.fill("fake_user@random.com")
        pwd_field.fill("BadPassword123!")
        page.locator("button:has-text('Sign In')").click()
        time.sleep(2)

        error_box = page.locator("div[data-testid='stAlert']:has-text('Invalid email or password')")
        assert error_box.is_visible(), "Expected generic error alert not displayed!"
        print("Generic error message displayed correctly without leaking account existence.")

        # ---------------------------------------------------------
        # Step 3: Forgot Password Navigation & Request
        # ---------------------------------------------------------
        print("\n3. Testing Forgot Password flow...")
        forgot_btn = page.locator("button:has-text('Forgot Password?')")
        forgot_btn.click()
        time.sleep(2)

        recovery_header = page.locator("text=Password Recovery")
        assert recovery_header.is_visible(), "Password Recovery view not displayed!"

        shot09 = str(SCREENSHOTS_DIR / "09_forgot_password_screen.png")
        page.screenshot(path=shot09, full_page=False)
        results["screenshot_09_forgot_pwd"] = shot09
        print(f"Saved Screenshot 09: {shot09}")

        # Clear any prior reset request records for testing
        from app.auth import get_auth_db
        conn = get_auth_db()
        conn.cursor().execute("DELETE FROM reset_request_attempts WHERE identifier = ?", (settings.ADMIN_EMAIL,))
        conn.commit()
        conn.close()

        # Submit admin email for reset
        recovery_email_input = page.locator("input[aria-label='Registered Administrator Email']")
        recovery_email_input.fill(settings.ADMIN_EMAIL)
        page.locator("button:has-text('Send Reset Link')").click()

        confirm_alert = page.locator("text=If the email address matches")
        confirm_alert.wait_for(timeout=15000)
        assert confirm_alert.is_visible(), "Generic confirmation alert not displayed!"
        print("Password reset request submitted; generic confirmation displayed.")

        # ---------------------------------------------------------
        # Step 4: Password Reset Page via Token Link
        # ---------------------------------------------------------
        print("\n4. Navigating to password reset link with token...")
        # Generate fresh token
        raw_token = generate_password_reset_token(settings.ADMIN_EMAIL)
        reset_url = f"http://127.0.0.1:8501/?action=reset_password&token={raw_token}"
        page.goto(reset_url, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        reset_header = page.locator("text=Set New Password")
        reset_header.wait_for(timeout=10000)
        assert reset_header.is_visible(), "Set New Password view not displayed!"

        shot10 = str(SCREENSHOTS_DIR / "10_reset_password_screen.png")
        page.screenshot(path=shot10, full_page=False)
        results["screenshot_10_reset_pwd"] = shot10
        print(f"Saved Screenshot 10: {shot10}")

        # Set new password
        new_test_pwd = "AdminVerifiedPass2026!#"
        new_pwd_input = page.locator("input[aria-label='New Password']")
        confirm_pwd_input = page.locator("input[aria-label='Confirm New Password']")

        new_pwd_input.fill(new_test_pwd)
        confirm_pwd_input.fill(new_test_pwd)
        page.locator("button:has-text('Update Password')").click()

        success_alert = page.locator("text=Password updated successfully")
        success_alert.wait_for(timeout=15000)
        assert success_alert.is_visible(), "Password update success alert not displayed!"
        print("Password successfully updated via reset token.")

        # Proceed to Sign In by navigating back to clean base URL
        page.goto("http://127.0.0.1:8501", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        login_header = page.locator("text=Administrator Sign In")
        login_header.wait_for(timeout=10000)
        assert login_header.is_visible(), "Administrator Sign In view not loaded after password reset!"

        # ---------------------------------------------------------
        # Step 5: Sign In with New Password & Verify Dashboard
        # ---------------------------------------------------------
        print("\n5. Signing in with new password...")
        email_field = page.locator("input[aria-label='Administrator Email']")
        pwd_field = page.locator("input[aria-label='Password']")

        email_field.fill(settings.ADMIN_EMAIL)
        pwd_field.fill(new_test_pwd)
        page.locator("button:has-text('Sign In')").click()

        # Verify Authenticated Dashboard
        chat_input = page.locator("[data-testid='stChatInput']")
        chat_input.wait_for(timeout=15000)
        assert chat_input.is_visible(), "Chat input not visible after authentication!"
        print("Authenticated successfully: Chat input is active.")

        sidebar = page.locator("[data-testid='stSidebar']")
        sidebar_text = sidebar.inner_text()
        assert settings.ADMIN_EMAIL in sidebar_text, "Admin email not displayed in sidebar!"
        assert "University Email" not in sidebar_text, "University Email must not be present in sidebar!"
        assert "Student Settings" in sidebar_text, "Student Settings section missing!"

        shot11 = str(SCREENSHOTS_DIR / "11_authenticated_dashboard.png")
        page.screenshot(path=shot11, full_page=False)
        results["screenshot_11_dashboard"] = shot11
        print(f"Saved Screenshot 11: {shot11}")

        # ---------------------------------------------------------
        # Step 6: Test Logout Flow
        # ---------------------------------------------------------
        print("\n6. Testing Administrator Logout...")
        logout_btn = sidebar.locator("button:has-text('Logout')")
        logout_btn.click()

        # Confirm returned to Sign In view
        login_header_after = page.locator("text=Administrator Sign In")
        login_header_after.wait_for(timeout=15000)
        assert login_header_after.is_visible(), "Login screen not visible after logout!"
        assert not page.locator("[data-testid='stChatInput']").is_visible(), "Chat input visible after logout!"
        print("Successfully logged out. Session invalidated; returned to Sign In.")

        browser.close()

    # Revert password to initial for future tests
    orig_pwd = settings.ADMIN_INITIAL_PASSWORD or "AdminSecurePass2026!"
    t_revert = generate_password_reset_token(settings.ADMIN_EMAIL)
    reset_password_with_token(t_revert, orig_pwd)
    print("Reverted administrator password to standard initial password.")

    # Save results json
    results_path = Path("D:/rag-mcp-assistant/audit/phase8_auth_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved verification audit records to: {results_path}")
    print("\nALL LIVE BROWSER AUTHENTICATION CHECKS PASSED!")

if __name__ == "__main__":
    verify_live_auth_flow()
