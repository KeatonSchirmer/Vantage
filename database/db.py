from pymongo import MongoClient
import certifi

MONGO_URI = 'mongodb+srv://StudentVantage:Thunder1589@studentvantage.rqum23o.mongodb.net/?retryWrites=true&w=majority&appName=StudentVantage' 

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
    )


db = client["StudentVantage"]
users = db["users"]
applications = db["applications"]
search_results = db["search_results"]
messages = db["messages"]
saved_listings = db["saved_listings"]
