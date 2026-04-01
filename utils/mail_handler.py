import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ────────────────────────────────────────────────
#  CHANGE THESE THREE LINES ONLY
# ────────────────────────────────────────────────
YOUR_EMAIL      = "sed3718@gmail.com"          # ← your Gmail address
APP_PASSWORD    = "alfp zktk xolh bevs"    # ← the one you just generated
TO_EMAIL        = 'sadikemreduzgun@gmail.com' #YOUR_EMAIL                     # or another address if you want

# Optional: customize these
SUBJECT         = "Test Alert from Python Script"
BODY            = "Hey Sadık!\n\nThis is a test message sent from your server in Ankara at " \
                  "around midnight.\nServer is up and running. 😎\n\nCheers!"

# ────────────────────────────────────────────────
# No need to change anything below here
# ────────────────────────────────────────────────

def send_mail(subject, body, from_m='sed3718@gmail.com', to_m='sadikemreduzgun@gmail.com'):
    msg = MIMEMultipart()
    msg["From"]    = YOUR_EMAIL
    msg["To"]      = TO_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        # Use SSL on port 465 (recommended & simpler)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(YOUR_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print("Email sent successfully! Check your inbox/spam.")
    except Exception as e:
        print(f"Failed to send email: {e}")

# Run it
if __name__ == "__main__":
    send_mail(SUBJECT, BODY)
