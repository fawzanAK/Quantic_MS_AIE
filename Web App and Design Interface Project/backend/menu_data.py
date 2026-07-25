"""Static menu content. Kept server-side so the same data can later be moved into a
real table without changing the frontend contract."""

MENU = {
    "Appetizers": [
        {"name": "Burrata & Heirloom Tomato", "price": 18, "description": "Basil oil, aged balsamic, sourdough crostini"},
        {"name": "Seared Scallops", "price": 22, "description": "Cauliflower puree, brown butter, capers"},
        {"name": "Roasted Beet Salad", "price": 15, "description": "Goat cheese, candied walnuts, arugula"},
    ],
    "Entrees": [
        {"name": "Pan-Seared Duck Breast", "price": 38, "description": "Cherry gastrique, farro, roasted root vegetables"},
        {"name": "Braised Short Rib", "price": 34, "description": "Truffle polenta, red wine jus, gremolata"},
        {"name": "Wild Mushroom Risotto", "price": 27, "description": "Parmesan, white truffle oil (v)"},
    ],
    "Desserts": [
        {"name": "Creme Brulee", "price": 12, "description": "Madagascar vanilla, torched sugar"},
        {"name": "Flourless Chocolate Torte", "price": 13, "description": "Espresso anglaise, candied hazelnut"},
    ],
    "Beverages": [
        {"name": "Reserve Cabernet, glass", "price": 16, "description": "Napa Valley, 2019"},
        {"name": "Sparkling Elderflower", "price": 8, "description": "Non-alcoholic"},
    ],
}
