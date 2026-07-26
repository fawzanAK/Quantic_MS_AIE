"""Static menu content, matching the SRS-specified items and prices exactly.
Kept server-side so it can later be moved into a real table without changing
the frontend contract."""

MENU = {
    "Starters": [
        {"name": "Bruschetta", "price": 8.50, "description": "Fresh tomatoes, basil, olive oil, and toasted baguette slices"},
        {"name": "Caesar Salad", "price": 9.00, "description": "Crisp romaine with homemade Caesar dressing"},
    ],
    "Main Courses": [
        {"name": "Grilled Salmon", "price": 22.00, "description": "Served with lemon butter sauce and seasonal vegetables"},
        {"name": "Ribeye Steak", "price": 28.00, "description": "12 oz prime cut with garlic mashed potatoes"},
        {"name": "Vegetable Risotto", "price": 18.00, "description": "Creamy Arborio rice with wild mushrooms"},
    ],
    "Desserts": [
        {"name": "Tiramisu", "price": 7.50, "description": "Classic Italian dessert with mascarpone"},
        {"name": "Cheesecake", "price": 7.00, "description": "Creamy cheesecake with berry compote"},
    ],
    "Beverages": [
        {"name": "Red Wine (Glass)", "price": 10.00, "description": "A selection of Italian reds"},
        {"name": "White Wine (Glass)", "price": 9.00, "description": "Crisp and refreshing"},
        {"name": "Craft Beer", "price": 6.00, "description": "Local artisan brews"},
        {"name": "Espresso", "price": 3.00, "description": "Strong and aromatic"},
    ],
}
