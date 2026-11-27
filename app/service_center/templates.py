"""Business templates. A template is only a starting point: the owner can change every field
(by voice/text description or in the settings form). Add a new business type by adding an entry."""

TEMPLATES = {
    "repair": {
        "label": "Phone / electronics repair",
        "name": "Mysuru Mobile Care", "agent_name": "Priya",
        "open": "10:00", "close": "20:00", "slot_minutes": 30, "closed_days": ["Sunday"], "break": ["13:30", "14:30"],
        "features": {"bookings": True, "orders": False, "records": True},
        "words": {"booking": "repair appointment", "record": "repair", "records": "Repairs in shop",
                  "purpose": "device and problem"},
        "info": ("Phone, laptop and tablet repairs. Water damage check is free; repair price after inspection. "
                 "3 months warranty on parts. Address: 12, Sayyaji Rao Road, Mysuru, near Clock Tower."),
        "catalog": [["Screen replacement", 1500, "job", "about 1 hour"],
                    ["Battery replacement", 1200, "job", "30 minutes"],
                    ["Charging port repair", 800, "job", "45 minutes"]],
        "records": [["J1001", "9876543210", "Ravi", "Samsung Galaxy S23", "Screen broken", "Ready for pickup", 1500, 0],
                    ["J1002", "9123456780", "Lakshmi", "iPhone 13", "Battery drains fast", "In repair", 1200, 1],
                    ["J1003", "9988776655", "Arun", "Dell laptop", "Not charging", "Waiting for spare part", 800, 3]],
        "steps": "Ask the device and the problem, tell the price if listed, then offer an appointment.",
    },
    "grocery": {
        "label": "Grocery / kirana store",
        "name": "Annapoorna Kirana Store", "agent_name": "Kavya",
        "open": "07:00", "close": "21:30", "slot_minutes": 60, "closed_days": [], "break": ["14:00", "15:00"],
        "features": {"bookings": False, "orders": True, "records": True},
        "words": {"booking": "delivery slot", "record": "order", "records": "Orders", "purpose": "items"},
        "info": ("Home delivery within 3 km, free above 300 rupees, otherwise 30 rupees. Delivery in about 1 hour. "
                 "Payment: cash or UPI on delivery. Address: 5th Main, Vijayanagar, Mysuru."),
        "catalog": [["Sona masoori rice", 60, "1 kg", "in stock"], ["Toor dal", 150, "1 kg", "in stock"],
                    ["Sunflower oil", 145, "1 litre", "in stock"], ["Milk (Nandini)", 27, "500 ml", "in stock"],
                    ["Sugar", 45, "1 kg", "in stock"], ["Atta", 55, "1 kg", "out of stock"],
                    ["Eggs", 72, "dozen", "in stock"], ["Onion", 40, "1 kg", "in stock"]],
        "records": [["O2001", "9876543210", "Ravi", "Rice 5 kg, oil 1 L", "Home delivery", "Out for delivery", 445, 0],
                    ["O2002", "9123456780", "Lakshmi", "Milk 2, eggs 1 dozen", "Pickup", "Ready for pickup", 126, 0]],
        "steps": ("Help the caller order: for each item check search_catalog for price and stock, repeat the full "
                  "list with the total, ask pickup or home delivery (and the address for delivery), then place_order "
                  "after they say yes. Never take an item that is out of stock; suggest what is available."),
    },
    "clinic": {
        "label": "Clinic / doctor",
        "name": "Sri Lakshmi Clinic", "agent_name": "Anitha",
        "open": "09:30", "close": "20:00", "slot_minutes": 15, "closed_days": ["Sunday"], "break": ["13:00", "16:00"],
        "features": {"bookings": True, "orders": False, "records": False},
        "words": {"booking": "doctor appointment", "record": "visit", "records": "Visits", "purpose": "reason for visit"},
        "info": ("Dr. Ramesh, MBBS MD (general physician). Consultation 300 rupees. Morning 9:30 to 1, evening 4 to 8. "
                 "For emergencies, tell the caller to call 108 or go to the nearest hospital immediately."),
        "catalog": [["Consultation", 300, "visit", ""], ["Blood sugar test", 100, "test", "results in 15 minutes"]],
        "records": [],
        "steps": ("Ask the patient's name and the reason for the visit (never give medical advice or diagnosis), "
                  "then offer appointment times. Emergencies: tell them to call 108 immediately."),
    },
    "salon": {
        "label": "Salon / beauty parlour",
        "name": "Glow Unisex Salon", "agent_name": "Divya",
        "open": "10:00", "close": "21:00", "slot_minutes": 30, "closed_days": ["Tuesday"], "break": ["14:00", "14:30"],
        "features": {"bookings": True, "orders": False, "records": False},
        "words": {"booking": "salon appointment", "record": "visit", "records": "Visits", "purpose": "service"},
        "info": "Unisex salon. Address: Kuvempunagar, Mysuru.",
        "catalog": [["Haircut (men)", 150, "service", "30 minutes"], ["Haircut (women)", 350, "service", "45 minutes"],
                    ["Facial", 800, "service", "1 hour"], ["Bridal makeup", 8000, "service", "book 1 week ahead"]],
        "records": [],
        "steps": "Ask which service, tell the price, then offer appointment times.",
    },
    "restaurant": {
        "label": "Restaurant / hotel",
        "name": "Mylari Tiffin Room", "agent_name": "Ramya",
        "open": "07:00", "close": "22:00", "slot_minutes": 30, "closed_days": [], "break": ["15:30", "18:00"],
        "features": {"bookings": True, "orders": True, "records": True},
        "words": {"booking": "table booking", "record": "order", "records": "Orders", "purpose": "number of people"},
        "info": "Pure veg. Parcel and home delivery within 2 km (delivery 40 rupees). Table booking for 2 to 12 people.",
        "catalog": [["Masala dosa", 80, "plate", "in stock"], ["Idli vada", 60, "plate", "in stock"],
                    ["Filter coffee", 30, "cup", "in stock"], ["Veg meals", 150, "plate", "lunch only, 12 to 3:30"]],
        "records": [],
        "steps": ("For a table: ask how many people, then offer times. For food orders: check each item with "
                  "search_catalog, repeat the list with the total, ask pickup or delivery, then place_order after yes."),
    },
    "custom": {
        "label": "Other business (custom)",
        "name": "My Business", "agent_name": "Sahaaya",
        "open": "09:00", "close": "18:00", "slot_minutes": 30, "closed_days": ["Sunday"], "break": ["13:00", "14:00"],
        "features": {"bookings": True, "orders": False, "records": False},
        "words": {"booking": "appointment", "record": "request", "records": "Requests", "purpose": "purpose"},
        "info": "Describe your business, services and prices here.",
        "catalog": [], "records": [],
        "steps": "Understand what the caller needs, answer from the business info, and offer an appointment if useful.",
    },
}
