import os
import json
import requests
from flask import Flask, request, jsonify

# Initialize Flask app container
app = Flask(__name__)

# System Configurations - Load securely via Render Environment Variables
ODOO_URL = os.environ.get("ODOO_URL", "https://odoo.com")
ODOO_DB = os.environ.get("ODOO_DB", "efixnow")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")
META_WA_TOKEN = os.environ.get("META_WA_TOKEN")
META_PHONE_ID = os.environ.get("META_PHONE_ID")

class OdooCloudConnector:
    def __init__(self, url, db, username, password):
        self.url = f"{url.rstrip('/')}/jsonrpc"
        self.db = db
        self.username = username
        self.password = password
        self.uid = self._authenticate()

    def _authenticate(self):
        """ Logs into Odoo Online and retrieves the user ID token """
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "authenticate",
                "args": [self.db, self.username, self.password, {}]
            },
            "id": 1
        }
        try:
            response = requests.post(self.url, json=payload, timeout=10).json()
            if "error" in response:
                print(f"Odoo Auth Error Response: {response['error']}")
                return None
            return response.get("result")
        except Exception as e:
            print(f"Failed to connect to Odoo Auth API: {str(e)}")
            return None

    def execute(self, model, method, *args, **kwargs):
        """ Executes standard Odoo ORM methods remotely """
        if not self.uid:
            print("Authentication missing. Cannot execute ORM methods.")
            return None
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [self.db, self.uid, self.password, model, method, args, kwargs]
            },
            "id": 2
        }
        try:
            res = requests.post(self.url, json=payload, timeout=10).json()
            if "error" in res:
                print(f"Odoo ORM Error on {model}.{method}:", res["error"])
                return None
            return res.get("result")
        except Exception as e:
            print(f"Failed to execute Odoo API request: {str(e)}")
            return None

# Initialize connection instance to Odoo
odoo = OdooCloudConnector(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS)

# Local ephemeral memory tracking active user checkout steps (Phone -> State Map)
USER_STATES = {}

def send_wa_message(to_phone, text_body):
    """ Dispatches a standard interactive text payload to Meta's Cloud API Graph nodes """
    url = f"https://facebook.com{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text_body}
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to push message via Meta HTTP Post: {str(e)}")

@app.route('/webhook', methods=['GET'])
def webhook_verification():
    """ Baseline direct echo verification route for Meta Developer handshakes """
    verify_token = os.environ.get("WEBHOOK_VERIFY_TOKEN", "efixnow_secret_token")
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
     if challenge:
        return str(challenge), 200
    return 'Verification Gate Active', 200
    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return challenge, 200
        return 'Forbidden', 403
    return 'Bad Request', 400

@app.route('/webhook', methods=['POST'])
def handle_whatsapp_traffic():
    """ Main event router parsing incoming text interactions """
    data = request.get_json()
    
    try:
        entry = data['entry'][0]['changes'][0]['value']
        if 'messages' not in entry:
            return jsonify({"status": "no_messages"}), 200
            
        message_data = entry['messages'][0]
        sender_phone = message_data['from']
        message_text = message_data['text']['body'].strip()
    except (KeyError, IndexError):
        return jsonify({"status": "invalid_payload"}), 200

    # Read current state tracker memory path
    current_state = USER_STATES.get(sender_phone, "START")

    # STEP 1: INITIAL ENTRY GATE (Shop UID Check)
    if current_state == "START":
        if message_text.upper() == "EFX-001":
            # Direct API look-up scanning for the Shop UID inside your custom table
            # Adjust the model string name to match your Odoo Studio configuration technical name exactly
            shop_records = odoo.execute('x_studio_partner_shop_agent', 'search_read', 
                                        [('x_studio_shop_unique_id', '=', 'EFX-001')], ['name'])
            
            if shop_records:
                shop_name = shop_records[0]['name']
                
                # Instantly seed a raw custom draft contact card inside Odoo via external JSON-RPC
                partner_id = odoo.execute('res.partner', 'create', {
                    'name': f"Pending Registration ({sender_phone})",
                    'phone': f"+{sender_phone}",
                    'x_studio_referred_by_shop': shop_records[0]['id']
                })
                
                USER_STATES[sender_phone] = f"WAITING_FOR_NAME:{partner_id}"
                
                send_wa_message(sender_phone, 
                                f"🔥 Welcome to Efixnow Device Rescue Membership! 🔥\n\n"
                                f"We have successfully locked in your location code at *{shop_name}*. "
                                f"By completing your registration today, you unlock 1 Free Premium Screen Protector or Cover immediately at this counter! 🎁\n\n"
                                f"Let's secure your membership slots. Please type your *Full Official Name* to begin:")
            else:
                send_wa_message(sender_phone, "❌ Shop profile initialization pending. Please confirm the shop code text details on the counter placard:")
        else:
            send_wa_message(sender_phone, "👋 Welcome to Efixnow. Please enter a valid Partner Shop Agent UID code to begin your onboarding journey:")
        
        return jsonify({"status": "processed"}), 200

    # Parse status tokens to fetch active record profile hooks
    state_parts = current_state.split(":")
    step_name = state_parts[0]
    partner_id = int(state_parts[1]) if len(state_parts) > 1 else None

    # STEP 2: CUSTOMER NAME PARSING
    if step_name == "WAITING_FOR_NAME":
        odoo.execute('res.partner', 'write', [partner_id], {'name': message_text})
        USER_STATES[sender_phone] = f"WAITING_FOR_REFERRAL:{partner_id}"
        send_wa_message(sender_phone, f"Thank you, {message_text}! 🤝\n\n"
                                      f"Were you referred to Efixnow by an existing member?\n\n"
                                      f"🔹 If *YES*, please type their *Phone Number* (e.g., 0712345678).\n"
                                      f"🔹 If *NO*, please type exactly: *NO*")

    # STEP 3: CUSTOMER REFERRAL TRACKING LINK
    elif step_name == "WAITING_FOR_REFERRAL":
        if message_text.upper() != "NO":
            cleaned_phone = message_text.replace(" ", "")
            referrer = odoo.execute('res.partner', 'search', [('phone', 'ilike', cleaned_phone)], limit=1)
            if referrer:
                odoo.execute('res.partner', 'write', [partner_id], {'x_studio_referred_by_customer': referrer[0]})
        
        USER_STATES[sender_phone] = f"WAITING_FOR_TIER:{partner_id}"
        send_wa_message(sender_phone, "Got it! Now, please select your subscription package tier from our standard rate card. Choose a number choice below:\n\n"
                                      "1️⃣ *Essential Tier* ── 1 Device Slot (KES 250/mo)\n"
                                      "2️⃣ *Standard Tier* ── 2 Device Slots (KES 399/mo)\n"
                                      "3️⃣ *Premium Tier* ── 3 Device Slots (KES 499/mo)\n\n"
                                      "*Reply with 1, 2, or 3:*")

    # STEP 4: PACKAGE ALLOTMENT CONSTRAINTS SETTING
    elif step_name == "WAITING_FOR_TIER":
        tier_map = {"1": "Essential (1 Device)", "2": "Standard (2 Devices)", "3": "Premium (3 Devices)"}
        choice = message_text.strip()
        
        if choice in tier_map:
            odoo.execute('res.partner', 'write', [partner_id], {'x_studio_subscription_package_tier': tier_map[choice]})
            USER_STATES[sender_phone] = f"WAITING_FOR_SLOT_1:{partner_id}:{choice}"
            send_wa_message(sender_phone, f"✨ *Excellent choice! Your subscription tier covers multiple devices.* ✨\n\n"
                                          f"Let's configure your slots. What asset types are we protecting today?\n\n"
                                          f"Please select the asset type for your *First Slot* by typing a letter choice:\n"
                                          f"A) Phone\n"
                                          f"B) Laptop\n"
                                          f"C) Tablet\n"
                                          f"D) PC\n\n"
                                          f"*(TV / Smart Appliances Coming Soon!)*")
        else:
            send_wa_message(sender_phone, "⚠️ Please type only 1, 2, or 3 to lock in your membership tier selection:")

    # STEP 5: CAPTURING ASSET SLOTS LOOPS
    elif "WAITING_FOR_SLOT_" in step_name:
        slot_number = int(step_name.split("_")[1])
        total_slots = int(state_parts[2])
        type_map = {"A": "Phone", "B": "Laptop", "C": "Tablet", "D": "PC"}
