from flask import Flask, render_template, request, url_for, redirect, jsonify
import requests
import json
from firebase import firebase
import firebase_admin 
from firebase_admin import credentials, db
# Correct Code
from dotenv import load_dotenv
import os


load_dotenv()  # This loads the environment variables from the .env file.

firebase_url = os.getenv('FIREBASE_URL')
cred_path = os.getenv('FIREBASE_ADMIN_CREDENTIAL')

#firebase_url = 'https://strykbros-default-rtdb.europe-west1.firebasedatabase.app/'

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred, {
    'databaseURL': firebase_url
})


app = Flask(__name__)

# Add zip to Jinja environment so it can be used in templates
app.jinja_env.globals.update(zip=zip)

# function for retreives the latest cooupon_id from firebase
def get_latest_coupon_id():
    ref = db.reference('/coupons')
    query = ref.order_by_key().limit_to_last(1)
    snapshot = query.get()
    print(snapshot)

    if snapshot:
        latest_coupon_id_str = next(iter(snapshot))
        latest_coupon_id = int(latest_coupon_id_str)
        return latest_coupon_id
    else:
        print("No coupons found")


def get_all_coupons():
    ref = db.reference('/coupons')
    coupons = ref.get()
    if not coupons:
        print("No coupons found")
        return {}
    return coupons


def update_database():
    most_recent = get_latest_coupon_id()
    if most_recent is None:
        print("Error: Unable to retrieve the most recent coupon ID.")
        return
    print('most recent:', most_recent)

    # Increment the most recent coupon ID to check for new data
    next_coupon_id = most_recent + 1

    # Make the API request
    response = requests.get(f'https://api.spela.svenskaspel.se/draw/1/stryktipset/draws/{next_coupon_id}')
    data = response.json()

    if data['error'] is None:
        next_coupon_dict = {}
        for i in range(1,14):
            next_coupon_dict[i] = {'1': False, '2': False, 'x': False}
        
        # Writing coupon data
        path = f'/coupons/{next_coupon_id}/games'
        ref = db.reference(path)
        ref.set(next_coupon_dict)
        
        # Writing name 
        name = data['draw']['drawComment']
        path = f'/coupons/{next_coupon_id}/meta/name'
        ref = db.reference(path)
        ref.set(name)
        return jsonify({'status': 'success', 'data': next_coupon_dict})


@app.route('/')
def home():
    update_database()
    coupons = get_all_coupons()
    return render_template('home.html', coupons=coupons)


@app.route('/index', methods=['POST', 'GET'])
def index():
    firebase_config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
    }
     
    coupon_id = request.args.get('coupon_id', default=None)
    coupon_name = request.args.get('coupon_name', default=None)
    if not coupon_id:
        return "Coupon ID is required", 400
    
    games_checked_status = None
    if coupon_id:
        games_checked_status = db.reference(f'/coupons/{coupon_id}/games').get()

    response = requests.get(f'https://api.spela.svenskaspel.se/draw/1/stryktipset/draws/{coupon_id}') #/4844 specifies round
    
    data = response.json()
    state = db.reference(f'/coupons/{coupon_id}/meta/drawState').get()
    outcome = None

    # Retrive outcome if games are finished 
    if state == 'Finalized':
        outcome = str(db.reference(f'/coupons/{coupon_id}/meta/outcome').get())
    num_games = max(len(data), 13)

    game_descriptions = []
    odds = []
    sv_percentage = []
    checked_status = {}

    # Retreiving data from api and passing as lists
    for i in range(num_games):
        
        # Indexing of games in firebase start at 1, in api starts at 0. TODO: Determine which indexing to use. 
        game_id = i+1

        title = str(i + 1) + ". " + data['draw']['drawEvents'][i]['eventDescription'] 
        game_descriptions.append(title)

        game_odds = data['draw']['drawEvents'][i]['odds']
        odds.append(list(game_odds.values()))

        sv_per = data['draw']['drawEvents'][i]['svenskaFolket']
        sv_keys = ['one', 'x', 'two']
        
        # Retrieve values from these keys
        sv_dict = {key: sv_per.get(key, None) for key in sv_keys}
        sv_percentage.append(list(sv_dict.values()))
        
        checked_status[game_id] = games_checked_status[i+1]

    return render_template('index.html', 
                            game_descriptions=game_descriptions, 
                            odds=odds,
                            sv_percentage=sv_percentage,
                            checked_status=checked_status,
                            coupon_id=coupon_id,
                            coupon_name=coupon_name,
                            outcome=outcome,
                            firebase_config=firebase_config
                            )


@app.route('/update-selection/<coupon_id>/<game_id>/<selection_type>/<is_selected>', methods=['POST'])
def update_selection(game_id, selection_type, is_selected, coupon_id):
    print('game_id:', game_id, 'selection_type:', selection_type, 'is_selected:', is_selected)
    path = f'/coupons/{coupon_id}/games/{game_id}/{selection_type.lower()}'
    update_status = True if is_selected == 'true' else False

    ref = db.reference(path)
    ref.set(update_status)
    return jsonify({'status': 'success', 'data': update_status})



if __name__ == "__main__":
    app.run(debug=True)
    