from flask import Flask, render_template, request, redirect, jsonify, url_for
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User
from flask import session as login_session
import random
import string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
from functools import wraps
from flask.ext.sqlalchemy import SQLAlchemy

CLIENT_ID = json.loads(
    open('client_secret.json', 'r').read())['web']['client_id']

app = Flask(__name__)

#engine = create_engine('sqlite:///categorylist.db')
#Base.metadata.bind = engine

#DBSession = sessionmaker(bind=engine)
#session = DBSession()
SQLALCHEMY_DATABASE_URI = "postgresql://catalog:@52.37.79.166/catalogdb"
db = SQLAlchemy(app)
session = db.session

app.secret_key = 'qp_Xn0CqTwMPYljIIiujIMh_'


   # if 'username' not in login_session or login_session['username'] is None:
      #  return redirect('/login')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in login_session or login_session['username'] is None:
            return redirect('/login')
            print 'nay'
        else:
            print 'yay'
            return f(*args, **kwargs)
    return decorated_function

def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    print state
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secret.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['credentials'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    #flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = login_session['credentials']
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] != '200':
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))

    else:
        response = make_response(json.dumps('Logged out', 200))
    response.headers['Content-Type'] = 'application/json'
    login_session['credentials'] = None
    login_session['username'] = None
    return response


@app.route('/category/<int:category_id>/itemlist/JSON')
def itemlistJSON(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Item).filter_by(
        category_id=category_id).all()
    return jsonify(Items=[i.serialize for i in items])


@app.route('/category/<int:category_id>/itemlist/<int:item_id>/JSON')
def itemJSON(restaurant_id, item_id):
    item = (session.queryItem).filter_by(id=item_id).one()
    return jsonify(item=item.serialize)


@app.route('/category/JSON')
def categoriesJSON():
    categories = session.query(Category).all()
    return jsonify(categories=[c.serialize for c in categories])


# Show all restaurants
@app.route('/')
@app.route('/category/')
def showCategories():
    categories = session.query(Category).all()
    # return "This page will show all my restaurants"
    return render_template('categories.html', categories=categories)


# Create a new restaurant
@app.route('/category/new/', methods=['GET', 'POST'])
@login_required
def newCategory():
    if request.method == 'POST':
        newCategory = Category(
            name=request.form['name'], user_id=login_session['user_id'])
        session.add(newCategory)
        session.commit()
        return redirect(url_for('showCategories'))
    else:
        return render_template('newCategory.html')
    # return "This page will be for making a new category"

# Edit a category


@app.route('/category/<int:category_id>/edit/', methods=['GET', 'POST'])
@login_required
def editCategory(category_id):
    editedcategory = session.query(
        Category).filter_by(id=category_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedcategory.name = request.form['name']
            return redirect(url_for('showCategories'))
    else:
        return render_template(
            'editCategory.html', category=editedcategory)

    # return 'This page will be for editing category %s' % category_id

# Delete a category
@app.route('/category/<int:category_id>/delete/', methods=['GET', 'POST'])
@login_required
def deleteCategory(category_id):
    categoryToDelete = session.query(
        Category).filter_by(id=category_id).one()
    if request.method == 'POST':
        session.delete(categoryToDelete)
        session.commit()
        return redirect(
            url_for('showCategories', category_id=category_id))
    else:
        return render_template(
            'deleteCategory.html', category=categoryToDelete)
    # return 'This page will be for deleting category %s' % category_id


# Show a category
@app.route('/category/<int:category_id>/')
@app.route('/category/<int:category_id>/itemlist/')
def showItems(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Item).filter_by(
        category_id=category_id).all()
    creator = getUserInfo(category.user_id)
    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicitems.html', items=items, category=category, creator=creator)
    # return 'This page is the item list for category %s' % category_id
    else:
        return render_template('items.html', items=items, category=category, creator=creator)
# Create a new item

@app.route(
    '/category/<int:category_id>/itemlist/new/', methods=['GET', 'POST'])
@login_required
def newItem(category_id):
    if request.method == 'POST':
        newItem = Item(name=request.form['name'], description=request.form[
            'description'], imageurl=request.form['imageurl'],category_id=category_id, user_id=login_session['user_id'])
        session.add(newItem)
        session.commit()

        return redirect(url_for('showItems', category_id=category_id))
    else:
        return render_template('newitem.html', category_id=category_id)

    return render_template('newitem.html', category=category)
    # return 'This page is for making a new item for category %s'
    # %category_id

# Edit a item

@app.route('/category/<int:category_id>/itemlist/<int:item_id>/edit',
           methods=['GET', 'POST'])
@login_required
def editItem(category_id, item_id):
    editedItem = session.query(Item).filter_by(id=item_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['imageurl']:
            editedItem.imageurl = request.form['imageurl']
        session.add(editedItem)
        session.commit()
        return redirect(url_for('showItems', category_id=category_id))
    else:

        return render_template(
            'edititem.html', category_id=category_id, item_id=item_id, item=editedItem)

    # return 'This page is for editing item list item %s' % item_id

# Delete an item
@app.route('/category/<int:category_id>/itemlist/<int:item_id>/delete',
           methods=['GET', 'POST'])
@login_required
def deleteItem(category_id, item_id):
    itemToDelete = session.query(Item).filter_by(id=item_id).one()
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        return redirect(url_for('showItems', category_id=category_id))
    else:
        return render_template('deleteitem.html', item=itemToDelete)
    # return "This page is for deleting  item %s" % _id


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
