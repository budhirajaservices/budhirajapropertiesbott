import os
import csv
import json
from datetime import datetime, timedelta
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import firebase_admin
from firebase_admin import credentials, firestore, storage

# Configuration
BOT_TOKEN = "8253938305:AAFUdmflQn4avUjoleVERLr-YuuCAyCfURo"
ADMIN_CHAT_ID = "budhirajaproperties"

# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROPERTIES_FILE = os.path.join(BASE_DIR, "properties.csv")
LEADS_FILE = os.path.join(BASE_DIR, "leads.csv")
VISITS_FILE = os.path.join(BASE_DIR, "visits.csv")

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Initialize Firebase
def init_firebase():
    try:
        # Load the service account key
        with open('serviceAccountKey.json', 'r') as f:
            service_account = json.load(f)
        
        # Initialize Firebase with the service account
        cred = credentials.Certificate('serviceAccountKey.json')
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{service_account['project_id']}.appspot.com"
        })
        print("✅ Firebase initialized successfully")
        return firestore.client()
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing serviceAccountKey.json: {e}")
        return None
    except FileNotFoundError:
        print("❌ Error: serviceAccountKey.json not found in the project directory")
        return None
    except Exception as e:
        print(f"❌ Firebase initialization error: {e}")
        return None

# Initialize Firebase
db = init_firebase()

# User states for conversation handling
user_states = {}

def set_user_state(user_id, state, data=None):
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['state'] = state
    if data:
        user_states[user_id].update(data)

def get_user_state(user_id):
    return user_states.get(user_id, {})

def clear_user_state(user_id):
    if user_id in user_states:
        del user_states[user_id]

# Initialize data files
def init_files():
    # Create properties file if not exists
    if not os.path.exists(PROPERTIES_FILE):
        with open(PROPERTIES_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'type', 'purpose', 'title', 'description', 'price',
                'location', 'area', 'bedrooms', 'bathrooms', 'owner_name',
                'owner_contact', 'is_featured', 'created_at', 'images'
            ])
    
    # Create leads file if not exists
    if not os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'phone', 'property_id', 'message', 'created_at', 'status'
            ])
    
    # Create visits file if not exists
    if not os.path.exists(VISITS_FILE):
        with open(VISITS_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'property_id', 'visitor_name', 'visitor_phone',
                'visit_date', 'visit_time', 'status', 'created_at'
            ])

# Start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    welcome_text = f"""🏠 *Welcome to Budhiraja Properties!*

Buy, Sell or Rent properties with ease. How can I assist you today?"""
    
    # Create main menu keyboard
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🏠 Buy Property"),
        types.KeyboardButton("🏢 Rent Property"),
        types.KeyboardButton("🏗️ Sell Property"),
        types.KeyboardButton("🔥 Hot Deals"),
        types.KeyboardButton("� Inquiry Form"),
        types.KeyboardButton("📞 Contact Us")
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=markup,
        parse_mode='Markdown'
    )

# Handle main menu options
@bot.message_handler(func=lambda message: True)
def handle_menu(message):
    text = message.text
    user_id = message.chat.id
    
    # Clear any existing state when starting a new command
    clear_user_state(user_id)
    
    if text == "🏠 Buy Property":
        start_property_search(message, "sale")
    elif text == "🏢 Rent Property":
        start_property_search(message, "rent")
    elif text == "🏗️ Sell Property":
        start_property_listing(message)
    elif text == "🔥 Hot Deals":
        show_featured_properties(message)
    elif text == "� Inquiry Form":
        start_inquiry(message)
    elif text == "📞 Contact Us":
        show_contact_options(message)
    else:
        # If we get an unexpected message, send the welcome message
        send_welcome(message)

# Start property search flow
def start_property_search(message, purpose):
    try:
        user_id = message.chat.id
        set_user_state(user_id, 'awaiting_location', {'purpose': purpose})
        
        # Clear any existing keyboard
        markup = types.ReplyKeyboardRemove()
        
        # Ask for location
        msg = bot.send_message(
            user_id,
            f"📍 Please enter the location (city/area) where you want to {'buy' if purpose == 'sale' else 'rent'} a property:\n\nExample: 'Mumbai', 'South Delhi', 'Whitefield Bangalore'",
            reply_markup=markup
        )
        
        # Register the next step handler
        bot.register_next_step_handler(msg, process_search_location)
        
    except Exception as e:
        print(f"Error in start_property_search: {e}")
        bot.send_message(
            message.chat.id,
            "❌ An error occurred. Please try again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def process_search_location(message):
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text.lower() in ['cancel', '❌ cancel']:
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Validate location input
        location = message.text.strip()
        if not location or len(location) < 2:
            msg = bot.send_message(
                user_id,
                "❌ Please enter a valid location (at least 2 characters).\n\nExample: 'Mumbai', 'South Delhi', 'Whitefield Bangalore'"
            )
            bot.register_next_step_handler(msg, process_search_location)
            return
            
        # Update state with location
        set_user_state(user_id, 'awaiting_property_type', {
            'purpose': state.get('purpose'),
            'filters': {'location': location}
        })
        
        # Show property type options
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        property_types = ["🏡 House", "🏢 Flat", "🏗️ Plot", "🏬 Commercial", "🌾 Farmhouse"]
        markup.add(*property_types)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "🏠 What type of property are you looking for?\n\nPlease select one option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_search_type)
        
    except Exception as e:
        print(f"Error in process_search_location: {e}")
        bot.send_message(
            message.chat.id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_search_type(message):
    try:
        user_id = message.chat.id
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Validate user state
        if user_id not in user_states or 'filters' not in user_states[user_id]:
            bot.send_message(user_id, "⚠️ Session expired. Starting over...")
            send_welcome(message)
            return
            
        # Validate property type
        valid_types = ["🏡 House", "🏢 Flat", "🏗️ Plot", "🏬 Commercial", "🌾 Farmhouse"]
        if message.text not in valid_types:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add(*[types.KeyboardButton(t) for t in valid_types] + [types.KeyboardButton("❌ Cancel")])
            
            msg = bot.send_message(
                user_id,
                "❌ Please select a valid property type from the options below:",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, process_search_type)
            return
            
        # Store the selected type (without emoji for consistency)
        type_mapping = {
            "🏡 House": "House",
            "🏢 Flat": "Flat",
            "🏗️ Plot": "Plot",
            "🏬 Commercial": "Commercial",
            "🌾 Farmhouse": "Farmhouse"
        }
        
        user_states[user_id]['filters']['type'] = type_mapping.get(message.text, message.text)
        
        # Ask for maximum price
        markup = types.ForceReply(selective=False)
        msg = bot.send_message(
            user_id,
            "💰 What's your maximum budget? (e.g., 50L, 1Cr, 2.5Cr)\n\nYou can type any budget amount or 'Any' to skip this filter.",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_search_price)
        
    except Exception as e:
        print(f"Error in process_search_type: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's try that again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def process_search_price(message):
    try:
        user_id = message.chat.id
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Validate user state
        if user_id not in user_states or 'filters' not in user_states[user_id]:
            bot.send_message(user_id, "⚠️ Session expired. Starting over...")
            send_welcome(message)
            return
            
        # Store the maximum budget
        user_states[user_id]['filters']['max_budget'] = message.text.strip()
        
        # Ask for minimum area
        markup = types.ForceReply(selective=False)
        msg = bot.send_message(
            user_id,
            "📏 What's the minimum area you're looking for? (e.g., 500 sqft, 1000 sqft, 2000 sqft)\n\nYou can type any area amount or 'Any' to skip this filter.",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_search_area)
        
    except Exception as e:
        print(f"Error in process_search_price: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's try that again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def process_search_area(message):
    try:
        user_id = message.chat.id
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Validate user state
        if user_id not in user_states or 'filters' not in user_states[user_id]:
            bot.send_message(user_id, "⚠️ Session expired. Starting over...")
            send_welcome(message)
            return
            
        # Store the minimum area
        user_states[user_id]['filters']['min_area'] = message.text.strip()
        
        # Perform the search
        properties = search_properties(user_states[user_id]['filters'])
        
        # Show results
        show_property_results(properties, user_id)
        
        # Show options for next steps
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("🔄 New Search"),
            types.KeyboardButton("🏠 Main Menu")
        )
        
        msg = bot.send_message(
            user_id,
            "🔍 Search completed! What would you like to do next?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, handle_search_complete)
        
    except Exception as e:
        print(f"Error in process_search_area: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's try that again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def handle_search_complete(message):
    """Handle user action after search results are shown."""
    user_id = message.chat.id
    
    if message.text == "🔄 New Search":
        clear_user_state(user_id)
        send_welcome(message)
    elif message.text == "🏠 Main Menu":
        clear_user_state(user_id)
        send_welcome(message)
    else:
        # If we get an unexpected message, show the welcome message
        clear_user_state(user_id)
        send_welcome(message)

def load_properties():
    """Load properties from the CSV file."""
    properties = []
    try:
        if os.path.exists(PROPERTIES_FILE):
            with open(PROPERTIES_FILE, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                properties = list(reader)
    except Exception as e:
        print(f"Error loading properties: {e}")
    return properties

def search_properties(filters):
    """Search properties based on filters."""
    properties = load_properties()
    if not properties:
        return []
    
    filtered_properties = []
    for prop in properties:
        # Filter by location (case-insensitive partial match)
        if 'location' in filters and filters['location'].lower() not in prop.get('location', '').lower():
            continue
            
        # Filter by property type
        if 'type' in filters and filters['type'].lower() != prop.get('type', '').lower():
            continue
            
        # Filter by purpose (sale/rent)
        if 'purpose' in filters and filters['purpose'].lower() != prop.get('purpose', '').lower():
            continue
            
        # Filter by maximum price (simple comparison for now)
        if 'max_budget' in filters and filters['max_budget'].lower() != 'any':
            try:
                prop_price = float(prop.get('price', '0').replace(',', '').replace('₹', '').strip())
                max_price = float(filters['max_budget'].replace('L', '00000').replace('Cr', '0000000').replace(',', ''))
                if prop_price > max_price:
                    continue
            except (ValueError, AttributeError):
                pass
                
        filtered_properties.append(prop)
    
    return filtered_properties

def format_property(prop):
    """Format a property for display with inquiry button."""
    property_text = f"""
🏠 *{prop.get('title', 'No Title')}*
📍 {prop.get('location', 'Location not specified')}
💰 Price: ₹{prop.get('price', 'N/A')}
📏 Area: {prop.get('area', 'N/A')}
🛏️ {prop.get('bedrooms', 'N/A')} Beds | 🛁 {prop.get('bathrooms', 'N/A')} Baths

{prop.get('description', 'No description available.')}

📞 Contact: {prop.get('owner_name', 'N/A')} - {prop.get('owner_contact', 'N/A')}
"""
    
    # Create inline keyboard for inquiry
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 Inquire About This Property", 
                                        callback_data=f"inquiry_{prop.get('id')}"))
    
    return property_text, markup

def show_property_results(properties, user_id):
    """Display search results to the user with inquiry option."""
    if not properties:
        bot.send_message(
            user_id,
            "🔍 No properties found matching your criteria. Try adjusting your filters.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return
    
    # Limit the number of results to show
    max_results = 5
    properties_to_show = properties[:max_results]
    
    for prop in properties_to_show:
        try:
            property_text, markup = format_property(prop)
            bot.send_message(
                user_id,
                property_text,
                parse_mode='Markdown',
                reply_markup=markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"Error showing property: {e}")
    
    if len(properties) > max_results:
        bot.send_message(
            user_id,
            f"ℹ️ Showing {max_results} of {len(properties)} properties. Try being more specific with your search to see fewer, more relevant results."
        )

def save_property(property_data):
    """Save property to Firebase"""
    try:
        if not db:
            print("❌ Database not initialized")
            return None
            
        # Add timestamps
        property_data['created_at'] = firestore.SERVER_TIMESTAMP
        property_data['updated_at'] = firestore.SERVER_TIMESTAMP
        
        # Add to Firestore
        doc_ref = db.collection('properties').document()
        doc_ref.set(property_data)
        print(f"✅ Property saved to Firebase with ID: {doc_ref.id}")
        return doc_ref.id
        
    except Exception as e:
        print(f"❌ Error saving property to Firebase: {e}")
        return None

def save_visitor(visitor_data):
    """Save visitor details to Firebase"""
    try:
        if not db:
            print("❌ Database not initialized")
            return None
            
        visitor_data['created_at'] = firestore.SERVER_TIMESTAMP
        visitor_data['status'] = 'scheduled'
        
        doc_ref = db.collection('visits').document()
        doc_ref.set(visitor_data)
        print(f"✅ Visit scheduled with ID: {doc_ref.id}")
        return doc_ref.id
        
    except Exception as e:
        print(f"❌ Error saving visitor to Firebase: {e}")
        return None

def save_inquiry(inquiry_data):
    """Save inquiry details to Firebase"""
    try:
        if not db:
            print("❌ Database not initialized")
            return None
            
        inquiry_data['created_at'] = firestore.SERVER_TIMESTAMP
        inquiry_data['status'] = 'new'
        
        doc_ref = db.collection('inquiries').document()
        doc_ref.set(inquiry_data)
        print(f"✅ Inquiry saved with ID: {doc_ref.id}")
        return doc_ref.id
        
    except Exception as e:
        print(f"❌ Error saving inquiry to Firebase: {e}")
        return None

def start_property_listing(message):
    """Start the property listing process."""
    try:
        user_id = message.chat.id
        set_user_state(user_id, 'property_listing', {
            'step': 'type',
            'data': {}
        })
        
        # Ask for property type
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        property_types = ["🏡 House", "🏢 Flat", "🏗️ Plot", "🏬 Commercial", "🌾 Farmhouse"]
        markup.add(*[types.KeyboardButton(pt) for pt in property_types])
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        bot.send_message(
            user_id,
            "🏗️ Let's list your property! First, what type of property is it?\n\n"
            "Please select one option:",
            reply_markup=markup
        )
        
    except Exception as e:
        print(f"Error in start_property_listing: {e}")
        bot.send_message(
            message.chat.id,
            "❌ An error occurred. Please try again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def process_property_type(message):
    """Process the selected property type."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Map emoji to property type
        type_mapping = {
            "🏡 House": "House",
            "🏢 Flat": "Flat",
            "🏗️ Plot": "Plot",
            "🏬 Commercial": "Commercial",
            "🌾 Farmhouse": "Farmhouse"
        }
        
        property_type = type_mapping.get(message.text, message.text)
        
        # Update state
        state['data']['type'] = property_type
        state['step'] = 'purpose'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property purpose
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("🏠 For Sale"),
            types.KeyboardButton("🏢 For Rent"),
            types.KeyboardButton("❌ Cancel")
        )
        
        bot.send_message(
            user_id,
            f"🏠 Is this property for sale or rent?",
            reply_markup=markup
        )
        
    except Exception as e:
        print(f"Error in process_property_type: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'property_listing' and 
                                      get_user_state(message.chat.id).get('step') == 'type')
def handle_property_type(message):
    process_property_type(message)

def process_property_purpose(message):
    """Process the selected property purpose."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Map to purpose
        purpose_mapping = {
            "🏠 For Sale": "sale",
            "🏢 For Rent": "rent"
        }
        
        purpose = purpose_mapping.get(message.text, '').lower()
        if purpose not in ['sale', 'rent']:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add(
                types.KeyboardButton("🏠 For Sale"),
                types.KeyboardButton("🏢 For Rent"),
                types.KeyboardButton("❌ Cancel")
            )
            
            msg = bot.send_message(
                user_id,
                "❌ Please select a valid option:",
                reply_markup=markup
            )
            return
            
        # Update state
        state['data']['purpose'] = purpose
        state['step'] = 'title'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property title
        markup = types.ReplyKeyboardRemove()
        msg = bot.send_message(
            user_id,
            "✏️ Enter a title for your property listing (e.g., 'Beautiful 3BHK Apartment in City Center'):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_title)
        
    except Exception as e:
        print(f"Error in process_property_purpose: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'property_listing' and 
                                      get_user_state(message.chat.id).get('step') == 'purpose')
def handle_property_purpose(message):
    process_property_purpose(message)

def process_property_title(message):
    """Process the property title."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['title'] = message.text.strip()
        state['step'] = 'description'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property description
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "📝 Enter a detailed description of your property. Include key features, amenities, and any other important details:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_description)
        
    except Exception as e:
        print(f"Error in process_property_title: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_description(message):
    """Process the property description."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['description'] = message.text.strip()
        state['step'] = 'price'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property price
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "💰 Enter the price of your property (e.g., 50L, 1Cr, 2.5Cr):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_price)
        
    except Exception as e:
        print(f"Error in process_property_description: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_price(message):
    """Process the property price."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['price'] = message.text.strip()
        state['step'] = 'location'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property location
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "📍 Enter the location of your property (e.g., 'Mumbai', 'South Delhi', 'Whitefield Bangalore'):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_location)
        
    except Exception as e:
        print(f"Error in process_property_price: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_location(message):
    """Process the property location."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['location'] = message.text.strip()
        state['step'] = 'area'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property area
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "📏 Enter the area of your property (e.g., 500 sqft, 1000 sqft, 2000 sqft):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_area)
        
    except Exception as e:
        print(f"Error in process_property_location: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_area(message):
    """Process the property area."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['area'] = message.text.strip()
        state['step'] = 'bedrooms'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property bedrooms
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "🛏️ Enter the number of bedrooms in your property:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_bedrooms)
        
    except Exception as e:
        print(f"Error in process_property_area: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_bedrooms(message):
    """Process the property bedrooms."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['bedrooms'] = message.text.strip()
        state['step'] = 'bathrooms'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property bathrooms
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "🛁 Enter the number of bathrooms in your property:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_bathrooms)
        
    except Exception as e:
        print(f"Error in process_property_bedrooms: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_bathrooms(message):
    """Process the property bathrooms."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['bathrooms'] = message.text.strip()
        state['step'] = 'owner_name'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property owner name
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "👥 Enter your name as the property owner:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_owner_name)
        
    except Exception as e:
        print(f"Error in process_property_bathrooms: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_owner_name(message):
    """Process the property owner name."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['owner_name'] = message.text.strip()
        state['step'] = 'owner_contact'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask for property owner contact
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "📞 Enter your contact number as the property owner:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_owner_contact)
        
    except Exception as e:
        print(f"Error in process_property_owner_name: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_owner_contact(message):
    """Process the property owner contact."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        state['data']['owner_contact'] = message.text.strip()
        state['step'] = 'is_featured'
        set_user_state(user_id, 'property_listing', state)
        
        # Ask if property is featured
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("🔥 Yes, feature this property"),
            types.KeyboardButton("🙅‍♂️ No, don't feature this property"),
            types.KeyboardButton("❌ Cancel")
        )
        
        msg = bot.send_message(
            user_id,
            "🤔 Do you want to feature this property?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_property_is_featured)
        
    except Exception as e:
        print(f"Error in process_property_owner_contact: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

def process_property_is_featured(message):
    """Process if property is featured."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        # Check if user wants to cancel
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state
        if message.text == "🔥 Yes, feature this property":
            state['data']['is_featured'] = 'true'
        else:
            state['data']['is_featured'] = 'false'
        
        # Save property
        property_id = save_property(state['data'])
        
        # Send confirmation
        bot.send_message(
            user_id,
            f"✅ Your property has been listed successfully! Property ID: {property_id}",
            reply_markup=types.ReplyKeyboardRemove()
        )
        
        # Clear state and show welcome
        clear_user_state(user_id)
        send_welcome(message)
        
    except Exception as e:
        print(f"Error in process_property_is_featured: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Let's start over.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        clear_user_state(user_id)
        send_welcome(message)

# Update the main menu handler to use the new property listing flow
@bot.message_handler(func=lambda message: message.text == "🏗️ Sell Property")
def handle_sell_property(message):
    start_property_listing(message)

def start_inquiry(message, property_id=None):
    """Start the inquiry process for a property."""
    try:
        user_id = message.chat.id
        set_user_state(user_id, 'inquiry', {
            'step': 'name',
            'property_id': property_id
        })
        
        # Ask for visitor's name
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        bot.send_message(
            user_id,
            "👤 Please enter your full name:",
            reply_markup=markup
        )
        
    except Exception as e:
        print(f"Error in start_inquiry: {e}")
        bot.send_message(
            message.chat.id,
            "❌ An error occurred. Please try again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

def process_inquiry_name(message):
    """Process the visitor's name for the inquiry."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Validate name
        name = message.text.strip()
        if len(name) < 2:
            msg = bot.send_message(
                user_id,
                "❌ Please enter a valid name (at least 2 characters)."
            )
            bot.register_next_step_handler(msg, process_inquiry_name)
            return
            
        # Update state with name
        state['name'] = name
        state['step'] = 'phone'
        set_user_state(user_id, 'inquiry', state)
        
        # Ask for phone number
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("📱 Share Contact", request_contact=True))
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        msg = bot.send_message(
            user_id,
            "📱 Please share your phone number or type it manually:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_inquiry_phone)
        
    except Exception as e:
        print(f"Error in process_inquiry_name: {e}")
        handle_inquiry_error(user_id)

def process_inquiry_phone(message):
    """Process the visitor's phone number for the inquiry."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Get phone number from contact or text
        if message.contact and message.contact.phone_number:
            phone = message.contact.phone_number
        else:
            phone = message.text.strip()
            
        # Validate phone number
        if not phone or not phone.isdigit() or len(phone) < 10:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("📱 Share Contact", request_contact=True))
            markup.add(types.KeyboardButton("❌ Cancel"))
            
            msg = bot.send_message(
                user_id,
                "❌ Please enter a valid 10-digit phone number or use the 'Share Contact' button.",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, process_inquiry_phone)
            return
            
        # Update state with phone
        state['phone'] = phone
        state['step'] = 'message'
        set_user_state(user_id, 'inquiry', state)
        
        # Ask for message
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("❌ Cancel"))
        
        property_info = ""
        if state.get('property_id'):
            property_info = f"\n\nProperty ID: {state['property_id']}"
            
        msg = bot.send_message(
            user_id,
            f"💬 Please enter your message or questions about the property:{property_info}",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_inquiry_message)
        
    except Exception as e:
        print(f"Error in process_inquiry_phone: {e}")
        handle_inquiry_error(user_id)

def handle_inquiry_error(user_id):
    """Handle errors in the inquiry process."""
    bot.send_message(
        user_id,
        "❌ An error occurred. Let's start over.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    clear_user_state(user_id)
    send_welcome(user_id)

@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'inquiry' and 
                                      get_user_state(message.chat.id).get('step') == 'name')
def handle_inquiry_name(message):
    process_inquiry_name(message)

@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'inquiry' and 
                                      get_user_state(message.chat.id).get('step') == 'phone')
def handle_inquiry_phone(message):
    process_inquiry_phone(message)

@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'inquiry' and 
                                      get_user_state(message.chat.id).get('step') == 'message')
def handle_inquiry_message(message):
    process_inquiry_message(message)

def process_inquiry_message(message):
    """Process the visitor's message for the inquiry."""
    try:
        user_id = message.chat.id
        state = get_user_state(user_id)
        
        if message.text == "❌ Cancel":
            clear_user_state(user_id)
            send_welcome(message)
            return
            
        # Update state with message
        state['message'] = message.text.strip()
        
        # Save inquiry
        inquiry_id = save_inquiry(state)
        
        # Send confirmation
        bot.send_message(
            user_id,
            f"✅ Your inquiry has been sent successfully! Inquiry ID: {inquiry_id}",
            reply_markup=types.ReplyKeyboardRemove()
        )
        
        # Clear state and show welcome
        clear_user_state(user_id)
        send_welcome(message)
        
    except Exception as e:
        print(f"Error in process_inquiry_message: {e}")
        handle_inquiry_error(user_id)

def show_contact_options(message):
    """Display contact options to the user."""
    try:
        user_id = message.chat.id
        
        # Create inline keyboard for contact options
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📞 Call Us", callback_data="contact_call"),
            types.InlineKeyboardButton("💬 WhatsApp", callback_data="contact_whatsapp")
        )
        markup.add(
            types.InlineKeyboardButton("📧 Email Us", callback_data="contact_email"),
            types.InlineKeyboardButton("🏢 Visit Office", callback_data="contact_office")
        )
        
        # Send contact information
        contact_info = """
        📞 *Contact Us*
        
        We're here to help! Choose an option below or use the buttons to get in touch:
        
        • 📞 *Call:* +91 1234567890
        • 💬 *WhatsApp:* +91 1234567890
        • 📧 *Email:* info@budhirajaproperties.com
        • 🏢 *Office:* 123 Property Street, City, State, 123456
        • 🕒 *Hours:* Mon-Sat, 10:00 AM - 7:00 PM
        """
        
        bot.send_message(
            user_id,
            contact_info,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
    except Exception as e:
        print(f"Error in show_contact_options: {e}")
        bot.send_message(
            message.chat.id,
            "❌ An error occurred while loading contact options. Please try again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(message)

# Firebase Collection Management
def create_collection(collection_name, document_data):
    """
    Create a new collection in Firestore with an initial document.
    
    Args:
        collection_name (str): Name of the collection to create
        document_data (dict): Data for the initial document
    
    Returns:
        str: Document ID of the created document, or None if failed
    """
    try:
        if not db:
            print("❌ Database not initialized")
            return None
            
        doc_ref = db.collection(collection_name).document()
        doc_ref.set(document_data)
        print(f"✅ Collection '{collection_name}' created with document ID: {doc_ref.id}")
        return doc_ref.id
    except Exception as e:
        print(f"❌ Error creating collection: {e}")
        return None

def get_collection(collection_name):
    """
    Get all documents from a collection.
    
    Args:
        collection_name (str): Name of the collection
        
    Returns:
        list: List of document dictionaries, or empty list if error
    """
    try:
        if not db:
            print("❌ Database not initialized")
            return []
            
        docs = db.collection(collection_name).stream()
        return [{**doc.to_dict(), 'id': doc.id} for doc in docs]
    except Exception as e:
        print(f"❌ Error getting collection {collection_name}: {e}")
        return []

# Example admin command handler
@bot.message_handler(commands=['create_collection'])
def handle_create_collection(message):
    """Admin command to create a new collection."""
    try:
        # Basic admin check (you should implement proper admin verification)
        if str(message.chat.username) != ADMIN_CHAT_ID:
            bot.reply_to(message, "❌ Unauthorized. Admin access required.")
            return
            
        # Parse command: /create_collection collection_name
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /create_collection collection_name")
            return
            
        collection_name = parts[1].strip()
        
        # Create collection with a sample document
        doc_id = create_collection(collection_name, {
            'created_at': firestore.SERVER_TIMESTAMP,
            'created_by': message.chat.username,
            'description': f'Sample document for {collection_name} collection'
        })
        
        if doc_id:
            bot.reply_to(message, f"✅ Collection '{collection_name}' created successfully!")
        else:
            bot.reply_to(message, f"❌ Failed to create collection '{collection_name}'")
            
    except Exception as e:
        print(f"Error in handle_create_collection: {e}")
        bot.reply_to(message, "❌ An error occurred while creating the collection.")

# Add this handler for contact option callbacks
@bot.callback_query_handler(func=lambda call: call.data.startswith('contact_'))
def handle_contact_callback(call):
    try:
        user_id = call.message.chat.id
        action = call.data.split('_')[1]
        
        if action == 'call':
            bot.answer_callback_query(call.id, "Calling +91 1234567890")
            # You can use the telegram.phone_number_request to initiate a call
            bot.send_contact(
                user_id,
                phone_number="+911234567890",
                first_name="Budhiraja",
                last_name="Properties"
            )
            
        elif action == 'whatsapp':
            bot.answer_callback_query(call.id, "Opening WhatsApp...")
            whatsapp_url = "https://wa.me/911234567890"
            bot.send_message(
                user_id,
                f"💬 Chat with us on WhatsApp: [Click Here]({whatsapp_url})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
        elif action == 'email':
            bot.answer_callback_query(call.id, "Composing email...")
            email = "info@budhirajaproperties.com"
            subject = "Inquiry from Telegram Bot"
            body = "Hello, I have a question about your properties."
            mailto = f"mailto:{email}?subject={subject}&body={body}"
            bot.send_message(
                user_id,
                f"📧 Email us at: {email}\n\n"
                f"[Click here to compose email]({mailto})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
        elif action == 'office':
            bot.answer_callback_query(call.id, "Showing office location...")
            bot.send_location(
                user_id,
                latitude=28.6139,  # Example coordinates (Delhi, India)
                longitude=77.2090
            )
            bot.send_message(
                user_id,
                "🏢 *Our Office*\n\n"
                "123 Property Street\n"
                "New Delhi, 110001\n"
                "India\n\n"
                "📍 [Open in Google Maps](https://maps.app.goo.gl/example)",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
    except Exception as e:
        print(f"Error in handle_contact_callback: {e}")
        bot.send_message(
            user_id,
            "❌ An error occurred. Please try again.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        send_welcome(call.message)

# Initialize the bot
if __name__ == "__main__":
    print("🤖 Bot is starting...")
    init_files()
    print("✅ Data files initialized")
    print("🤖 Bot is running...")
    bot.polling(none_stop=True)
