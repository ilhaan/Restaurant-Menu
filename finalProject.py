from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Restaurant, MenuItem

# OAuth stuff
from flask import session as login_session
import random, string

# Imports for G-Connect stuff
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']

app = Flask(__name__)

engine = create_engine('sqlite:///restaurantmenu.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)

@app.route('/gconnect', methods = ['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter'), 401)
        response.headers['Connect-Type'] = 'application/json'
        print "The states match!"
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps('Failed to upgrade the authorization code'), 401)
        response.headers['Connect-Type'] = 'application/json'
        return response

    # Check that access token is valid
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s' % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])

    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 501)
        response.headers['contentType'] = 'application/json'

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps('Token\'s user ID doesn\'t match given user ID.'), 401)
        response.headers['Connect-Type'] = 'application/json'
        return response

    # Check to see if user is already logged in.
    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'), 200)
        response.headers['Connect-Type'] = 'application/json'

    # Store the access token in the session for later use.
    login_session['credentials'] = credentials
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt':'json'}
    answer = requests.get(userinfo_url, params = params)
    print answer.text
    data = json.loads(answer.text)

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    output = ''
    output += '<h1> Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src ="'
    output += login_session['picture']
    output += ' style = "width: 300px; height: 300px; border-radius: 150px; -webkit-border-radius: 150px; -moz-border-radius: 150px;"> '
    flash_message = "You are now logged in as %s" % login_session['username']
    flash(flash_message)
    return output

@app.route('/gdisconnect')
def gdisconnect():
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(json.dumps('Current user not connected'), 401)
        response.headers['Connect-Type'] = 'application/json'
        return response
    access_token = credentials.access_token
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset user's session
        del login_session['credentials']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected'), 200)
        response.headers['Connect-Type'] = 'application/json'
        return response

@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
    restaurants = session.query(Restaurant).all()
    return render_template('restaurants.html', restaurants = restaurants)

@app.route('/restaurant/new/', methods = ['GET', 'POST'])
def newRestaurant():
    if request.method == 'POST':
        newRestaurant = Restaurant(name = request.form['name'])
        session.add(newRestaurant)
        session.commit()
        flash("New restaurant created!")
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('newrestaurant.html')

@app.route('/restaurant/<int:restaurant_id>/edit/', methods = ['GET', 'POST'])
def editRestaurant(restaurant_id):
    editedRestaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedRestaurant.name = request.form['name']
        session.add(editedRestaurant)
        session.commit()
        flash_string = "%s has been edited" % editedRestaurant.name
        flash(flash_string)
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('editrestaurant.html', restaurant = editedRestaurant)

@app.route('/restaurant/<int:restaurant_id>/delete/', methods = ['GET', 'POST'])
def deleteRestaurant(restaurant_id):
    deletedRestaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    if request.method == 'POST':
        session.delete(deletedRestaurant)
        session.commit()
        flash_string = "%s has been deleted" % deletedRestaurant.name
        flash(flash_string)
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('deleterestaurant.html', restaurant = deletedRestaurant)

@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id)
    return render_template('menu.html', restaurant = restaurant, items = items)

@app.route('/restaurant/<int:restaurant_id>/menu/new/', methods = ['GET', 'POST'])
def newMenuItem(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    if request.method == 'POST':
        newItem = MenuItem(name = request.form['name'], restaurant_id = restaurant.id, description = request.form['description'], price = request.form['price'])
        session.add(newItem)
        session.commit()
        flash_string = "%s has been added to the menu" % newItem.name
        flash(flash_string)
        return redirect(url_for('showMenu', restaurant_id = restaurant.id))
    else:
        return render_template('newmenuitem.html', restaurant = restaurant)

@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit/', methods = ['GET', 'POST'])
def editMenuItem(menu_id, restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    editedItem = session.query(MenuItem).filter_by(id = menu_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        session.add(editedItem)
        session.commit()
        flash_string = "%s has been edited" % editedItem.name
        flash(flash_string)
        return redirect(url_for('showMenu', restaurant_id = restaurant.id))
    else:
        return render_template('editmenuitem.html', restaurant = restaurant, item = editedItem)

@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete/', methods = ['GET', 'POST'])
def deleteMenuItem(menu_id, restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    deletedItem = session.query(MenuItem).filter_by(id = menu_id).one()
    if request.method == 'POST':
        session.delete(deletedItem)
        session.commit()
        flash_string = "%s has been deleted" % deletedItem.name
        flash(flash_string)
        return redirect(url_for('showMenu', restaurant_id = restaurant.id))
    else:
        return render_template('deletemenuitem.html', restaurant = restaurant, item = deletedItem)

# API Endpoints
@app.route('/restaurant/JSON/')
def showRestaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(Restaurant = [i.serialize for i in restaurants])

@app.route('/restaurant/<int:restaurant_id>/menu/JSON/')
def showMenuJSON(restaurant_id):
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id)
    return jsonify(MenuItem = [i.serialize for i in items])

@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON/')
def showMenuItemJSON(restaurant_id, menu_id):
    Menu_Item = session.query(MenuItem).filter_by(id = menu_id).one()
    return jsonify(Menu_Item = Menu_Item.serialize)

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
