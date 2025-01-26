from flask import Flask, render_template, request, redirect, url_for, flash
from forms import DateSelectionForm, PaymentForm, BikeIDManagementForm, LockUnlockForm,  CreateBikeForm  # Add the new form classes
import shelve
import gpxpy
import os
import logging
import shelve
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from bikeclass import BikeProduct, Order, carparks, BikeID
from math import radians, sin, cos, sqrt, atan2
import os  # Required to access environment variables

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def extract_gpx_details(gpx_file_path):
    try:
        with open(gpx_file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        total_distance = 0
        start_time = None
        end_time = None
        carbon_emission_factor = 0.1  # kg CO2 per km

        for track in gpx.tracks:
            for segment in track.segments:
                for i in range(len(segment.points) - 1):
                    point1 = segment.points[i]
                    point2 = segment.points[i + 1]

                    # Calculate distance between points
                    total_distance += point1.distance_3d(point2)

                # Capture start and end time
                if segment.points:
                    if not start_time:
                        start_time = segment.points[0].time
                    end_time = segment.points[-1].time

        # Calculate total duration in hours
        if start_time and end_time and start_time < end_time:
            total_time = (end_time - start_time).total_seconds() / 3600  # Hours
        else:
            total_time = 0

        # Calculate average speed (safe check for zero time)
        # Only consider the first `speed` or `extensions` entry for speed, if available.
        avg_speed = sum([point.speed for point in segment.points if point.speed]) / len(segment.points) if segment.points else 0

        # Convert distance to kilometers
        total_distance_km = total_distance / 1000

        # Calculate total carbon emissions
        total_carbon_emissions = total_distance_km * carbon_emission_factor

        print(f"Total distance: {total_distance_km} km, Total time: {total_time} hours, Average speed: {avg_speed} km/h")

        return {
            "total_distance": round(total_distance_km, 2),
            "avg_speed": round(avg_speed, 2),
            "duration": f"{int(total_time)} hours {int((total_time % 1) * 60)} mins" if total_time > 0 else "N/A",
            "carbon_emissions": round(total_carbon_emissions, 2)
        }
    except Exception as e:
        print(f"Error processing GPX file: {e}")
        return {"total_distance": 0, "avg_speed": 0, "duration": "N/A", "carbon_emissions": 0}

def generate_svg_points(gpx_file_path):
    try:
        with open(gpx_file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        route_coordinates = [
            (point.latitude, point.longitude)
            for track in gpx.tracks
            for segment in track.segments
            for point in segment.points
        ]

        min_lat = min(coord[0] for coord in route_coordinates)
        max_lat = max(coord[0] for coord in route_coordinates)
        min_lon = min(coord[1] for coord in route_coordinates)
        max_lon = max(coord[1] for coord in route_coordinates)

        width_scale = 200  # Adjust scaling factor
        height_scale = 150  # Adjust scaling factor

        svg_points = " ".join([
            f"{((lon - min_lon) / (max_lon - min_lon) * width_scale)},{(max_lat - lat) / (max_lat - min_lat) * height_scale}"
            for lat, lon in route_coordinates
        ])
        return svg_points
    except Exception as e:
        print(f"Error generating SVG points: {e}")
        return ""

def load_env(file_path=".env"):
    try:
        # Print full absolute path
        import os
        full_path = os.path.abspath(file_path)
        print(f"Attempting to load .env from: {full_path}")
        print(f"File exists: {os.path.exists(full_path)}")
        
        with open(full_path, "r") as env_file:
            for line in env_file:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    print(f"Loading: {key}={value}")
                    os.environ[key.strip()] = value.strip()
        
        # Verify API key is loaded
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        print(f"Loaded API Key: {api_key}")
    except Exception as e:
        print(f"Detailed Error: {e}")
        print(f"Error Type: {type(e)}")
        
        
# Load the .env variables
load_env()

# Access the variables
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

            
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/createBike', methods=['GET', 'POST'])
def create_bike():
    create_bike_form = CreateBikeForm(request.form)

    if request.method == 'POST' and create_bike_form.validate():
        db = shelve.open('bike.db', 'c')
        bikes_dict = db.get('Bikes', {})

        file = request.files.get('upload_bike_image')
        filename = ''
        if file and file.filename != '':
            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        bike_id = len(bikes_dict) + 1
        bike_data = {
            "bike_id": bike_id,
            "bike_name": create_bike_form.bike_name.data,
            "upload_bike_image": filename,
            "price": float(create_bike_form.price.data),
            "transmission_type": create_bike_form.transmission_type.data,
            "seating_capacity": create_bike_form.seating_capacity.data,
            "engine_output": create_bike_form.engine_output.data,
            "stock_quantity": int(create_bike_form.stock_quantity.data),
        }

        bikes_dict[bike_id] = bike_data
        db['Bikes'] = bikes_dict
        db.close()

        flash("Bike created successfully!", "success")
        return redirect(url_for('retrieve_bikes'))
    return render_template('createBike.html', form=create_bike_form)


@app.route('/retrieveBikes')
def retrieve_bikes():
    db = shelve.open('bike.db', 'c')
    bikes_dict = db.get('Bikes', {})
    db.close()

    converted_bikes_dict = {
        bike_id: bike if isinstance(bike, dict) else bike.__dict__
        for bike_id, bike in bikes_dict.items()
    }
    return render_template('retrieveBikes.html', count=len(converted_bikes_dict), bikes=converted_bikes_dict)


@app.route('/updateBike/<int:id>/', methods=['GET', 'POST'])
def update_bike(id):
    update_bike_form = CreateBikeForm(request.form)

    # Open the database
    with shelve.open('bike.db', 'c') as db:
        bikes_dict = db.get('Bikes', {})
        bike = bikes_dict.get(id)

        if not bike:
            flash("Bike not found.", "error")
            return redirect(url_for('retrieve_bikes'))

        if request.method == 'POST' and update_bike_form.validate():
            # Update bike details
            bike["bike_name"] = update_bike_form.bike_name.data
            bike["price"] = float(update_bike_form.price.data)
            bike["transmission_type"] = update_bike_form.transmission_type.data
            bike["seating_capacity"] = update_bike_form.seating_capacity.data
            bike["engine_output"] = update_bike_form.engine_output.data
            bike["stock_quantity"] = int(update_bike_form.stock_quantity.data)

            # Handle image upload
            file = request.files.get('upload_bike_image')
            if file and file.filename != '':
                # Remove old image if it exists
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], bike.get("upload_bike_image", ""))
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)

                # Save new image
                from werkzeug.utils import secure_filename
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                bike["upload_bike_image"] = filename

            # Save updated bike to the database
            bikes_dict[id] = bike
            db['Bikes'] = bikes_dict

            flash("Bike updated successfully!", "success")
            return redirect(url_for('retrieve_bikes'))

        # Pre-fill the form with existing bike details
        update_bike_form.bike_name.data = bike["bike_name"]
        update_bike_form.price.data = bike["price"]
        update_bike_form.transmission_type.data = bike["transmission_type"]
        update_bike_form.seating_capacity.data = bike["seating_capacity"]
        update_bike_form.engine_output.data = bike["engine_output"]
        update_bike_form.stock_quantity.data = bike["stock_quantity"]

    return render_template('updateBikes.html', form=update_bike_form, bike=bike)


@app.route('/viewBikes')
def view_bikes():
    db = shelve.open('bike.db', 'r')
    bikes_dict = db.get('Bikes', {})
    db.close()

    return render_template('viewBikes.html', count=len(bikes_dict), bikes=bikes_dict)


@app.route('/deleteBike/<int:id>/', methods=['POST'])
def delete_bike(id):
    db = shelve.open('bike.db', 'c')
    bikes_dict = db.get('Bikes', {})

    if id in bikes_dict:
        del bikes_dict[id]
        db['Bikes'] = bikes_dict
        flash("Bike deleted successfully!", "success")
    else:
        flash("Bike not found.", "error")

    db.close()
    return redirect(url_for('retrieve_bikes'))

@app.route('/dashBoard', methods=['GET'])
def dashboard():
    # Load data from persistent storage
    with shelve.open('dashboard_data.db') as db:
        gpx_details = db.get('gpx_details', {"total_distance": 0, "avg_speed": 0, "carbon_emissions": 0, "duration": 0})
        bike_count = db.get('bike_count', 0)

    # Generate SVG points based on the last GPX file uploaded (if available)
    gpx_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'latest.gpx')
    if os.path.exists(gpx_file_path):
        svg_points = generate_svg_points(gpx_file_path)
    else:
        svg_points = ""

    # Weekly Leaderboard Data
    leaderboard = [
        {"name": "Jun Hao", "change": "up", "avatar": "J", "color": "#ff9aa2"},
        {"name": "Bryce", "change": "up", "avatar": "B", "color": "#9bcdf8"},
        {"name": "Rais", "change": "up", "avatar": "R", "color": "#c2c7ff"},
        {"name": "Wei Kiat", "change": "down", "avatar": "W", "color": "#d6d8db"}
    ]

    # Render the normal dashboard
    return render_template(
        'dashBoard.html',
        svg_points=svg_points,
        total_emissions=gpx_details["carbon_emissions"],
        bike_count=bike_count,
        total_miles=gpx_details["total_distance"],
        avg_speed=gpx_details["avg_speed"],
        duration=gpx_details["duration"],
        leaderboard=leaderboard
    )

import math

@app.route('/dashBoardAdmin', methods=['GET', 'POST'])
def dashboard_admin():
    # Initialize default values
    gpx_details = {"total_distance": 0, "avg_speed": 0, "carbon_emissions": 0, "duration": 0.0}
    bike_increment = 1  # Increment bike count by 1 for each upload

    if request.method == 'POST':
        gpx_file = request.files.get('gpx_file')

        with shelve.open('dashboard_data.db') as db:
            # Ensure keys exist in storage
            if 'gpx_details' not in db:
                db['gpx_details'] = gpx_details
            if 'bike_count' not in db:
                db['bike_count'] = 0

            if gpx_file and gpx_file.filename.endswith('.gpx'):
                gpx_upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'latest.gpx')  # Save as 'latest.gpx'
                gpx_file.save(gpx_upload_path)

                # Extract GPX details and update cumulative data
                new_gpx_details = extract_gpx_details(gpx_upload_path)

                # Parse the duration string safely
                duration_str = new_gpx_details.get('duration', "0 hours 0 mins")
                try:
                    # Extract hours and minutes from the string
                    hours = int(duration_str.split('hours')[0].strip())
                    minutes = int(duration_str.split('hours')[1].split('mins')[0].strip())
                    total_hours = hours + (minutes / 60)  # Convert to total hours
                    new_duration = math.ceil(total_hours)  # Round up to the nearest hour
                except (ValueError, IndexError):
                    new_duration = 0.0  # Default to 0 if parsing fails

                # Ensure `duration` is stored as a float
                current_gpx_details = db['gpx_details']
                try:
                    current_duration = float(current_gpx_details.get('duration', 0.0))
                except ValueError:
                    current_duration = 0.0  # Reset to 0.0 if the existing value is invalid

                current_gpx_details['duration'] = current_duration + new_duration
                current_gpx_details['total_distance'] += new_gpx_details['total_distance']
                current_gpx_details['avg_speed'] = (
                    (current_gpx_details['avg_speed'] + new_gpx_details['avg_speed']) / 2
                )
                current_gpx_details['carbon_emissions'] += new_gpx_details['carbon_emissions']
                db['gpx_details'] = current_gpx_details  # Save back to shelve

                # Increment bike count
                db['bike_count'] += bike_increment
                flash(f"GPX file '{gpx_file.filename}' uploaded and processed successfully!", "success")
            else:
                flash("Invalid file type. Please upload a valid GPX file.", "error")

    # Load data to render the admin dashboard
    with shelve.open('dashboard_data.db') as db:
        gpx_details = db.get('gpx_details', {"total_distance": 0, "avg_speed": 0, "carbon_emissions": 0, "duration": 0.0})
        bike_count = db.get('bike_count', 0)

    return render_template(
        'dashBoardAdmin.html',
        gpx_details=gpx_details,
        bike_count=bike_count
    )
@app.route('/resetDashboard', methods=['POST'])
def reset_dashboard():
    # Path to the shelve database
    shelve_path = 'dashboard_data.db'

    # Reset the shelve database
    with shelve.open(shelve_path, writeback=True) as db:
        db.clear()  # Clear all existing data
        db['gpx_details'] = {
            "total_distance": 0,
            "avg_speed": 0,
            "carbon_emissions": 0,
            "duration": 0.0
        }
        db['bike_count'] = 0

    flash("Dashboard has been reset to default values.", "success")
    return redirect('/dashBoardAdmin')

@app.route('/add_to_cart/<int:bike_id>', methods=['POST'])
def add_to_cart(bike_id):
    try:
        # Open the bike database to fetch bike details
        with shelve.open('bike.db', 'r') as db:
            bikes = db.get('Bikes', {})
            bike = bikes.get(bike_id)  # Fetch the bike by ID

        if not bike:
            flash("Bike not found", "error")
            return redirect(url_for('view_bikes'))

        logging.debug(f"Adding bike to cart: {bike}")

        # Open the cart database to add the bike
        with shelve.open('cart.db', 'c') as db:
            cart = db.get('cart', {})
            if bike_id in cart:
                cart[bike_id]['quantity'] += 1  # Increment quantity if the bike is already in the cart
            else:
                # Use BikeProduct attributes in the cart structure
                cart[bike_id] = {
                    'bike': bike,  # Store the bike object directly
                    'quantity': 1
                }
            db['cart'] = cart  # Save the updated cart
            logging.debug(f"Cart updated: {cart}")

        flash("Bike added to cart successfully!", "success")
        return redirect(url_for('checkout'))

    except Exception as e:
        logging.error(f"Error in add_to_cart: {e}")
        flash(f"Error adding to cart: {e}", "error")
        return redirect(url_for('view_bikes'))
    
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    form = DateSelectionForm()
    try:
        with shelve.open('bike.db', 'r') as db:
            bikes = db.get('Bikes', {})
        
        with shelve.open('cart.db', 'r') as db:
            cart = db.get('cart', {})
            
            if not cart:
                flash("No item in cart", "error")
                return redirect(url_for('view_bikes'))
            
            # Get the first (and only) item in the cart
            bike_id = list(cart.keys())[0]
            bike = bikes[bike_id]
            base_price = bike['price']
            
            if form.validate_on_submit():
                days = (form.end_date.data - form.start_date.data).days + 1
                total = base_price * days
                
                session['rental_info'] = {
                    'start_date': form.start_date.data.strftime('%Y-%m-%d'),
                    'end_date': form.end_date.data.strftime('%Y-%m-%d'),
                    'days': days,
                    'total': total
                }
                
                return redirect(url_for('payment'))
            
            return render_template('checkout.html', 
                                 form=form, 
                                 cart_items=[bike], 
                                 total=base_price)
    except Exception as e:
        logging.error(f"Error in checkout: {str(e)}", exc_info=True)
        flash("Error processing checkout", "error")
        return redirect(url_for('view_bikes'))
    
@app.route('/payment', methods=['GET', 'POST'])
def payment():
    form = PaymentForm()
    rental_info = session.get('rental_info')
    
    if not rental_info:
        flash("Please select rental dates first", "error")
        return redirect(url_for('checkout'))
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                with shelve.open('cart.db', 'r') as db:
                    cart = db.get('cart', {})
                    if not cart:
                        flash("Cart is empty", "error")
                        return redirect(url_for('view_bikes'))
                    
                # Generate order ID
                order_id = datetime.now().strftime('%Y%m%d%H%M%S')
                
                # Get rental dates from session
                rental_dates = {
                    'start_date': rental_info['start_date'],
                    'end_date': rental_info['end_date'],
                    'days': rental_info['days']
                }
                
                # Store user email in session
                session['user_email'] = form.email.data
                
                # Find nearest carpark if coordinates are provided
                nearest_carpark = None
                if form.latitude.data and form.longitude.data:
                    try:
                        nearest_carpark = find_nearest_carpark(
                            float(form.latitude.data),
                            float(form.longitude.data)
                        )
                    except ValueError as e:
                        logging.error(f"Error finding nearest carpark: {e}")
                        flash("Error processing location data", "error")
                        return render_template('payment.html', form=form, google_maps_api_key=GOOGLE_MAPS_API_KEY)
                
                # Compile customer information
                customer_info = {
                    'full_name': form.full_name.data,
                    'email': form.email.data,
                    'address': form.address.data,
                    'city': form.city.data,
                    'postal_code': form.postal_code.data,
                    'payment_info': {
                        'card_last_4': form.card_no.data[-4:],
                        'exp_date': form.exp_date.data
                    }
                }
                
                # Add carpark information if available
                if nearest_carpark:
                    customer_info['assigned_carpark'] = nearest_carpark
                
                # Create new order
                # In the payment route, modify the order creation section
                order = Order(
                    order_id=order_id,
                    items=dict(cart),  # Keep the entire cart dictionary
                    total=rental_info['total'],
                    customer_info=customer_info,
                    order_date=datetime.now(),
                    rental_dates=rental_dates
                )
                
                # Save order to database
                try:
                    with shelve.open('orders.db', 'c') as db:
                        orders = db.get('orders', {})
                        orders[order_id] = order
                        db['orders'] = orders
                except Exception as e:
                    logging.error(f"Error saving order to database: {e}")
                    flash("Error saving order", "error")
                    return render_template('payment.html', form=form, google_maps_api_key=GOOGLE_MAPS_API_KEY)
                
                # Clear session data
                session.pop('rental_info', None)
                
                # Clean up cart
                try:
                    with shelve.open('cart.db', 'c') as db:
                        if 'cart' in db:
                            del db['cart']
                except Exception as e:
                    logging.error(f"Error clearing cart: {e}")
                
                flash("Order placed successfully!", "success")
                return redirect(url_for('order_confirmation', order_id=order_id))
                
            except Exception as e:
                logging.error(f"Error processing payment: {e}", exc_info=True)
                flash("Error processing payment", "error")
                return render_template('payment.html', form=form, google_maps_api_key=GOOGLE_MAPS_API_KEY)
        else:
            logging.warning(f"Form validation failed: {form.errors}")
            return render_template('payment.html', form=form, google_maps_api_key=GOOGLE_MAPS_API_KEY)

    # GET request - render empty form
    return render_template('payment.html', form=form, google_maps_api_key=GOOGLE_MAPS_API_KEY)
@app.route('/orders')
def view_orders():
    """View all orders"""
    try:
        with shelve.open('orders.db', 'r') as db:
            orders = db.get('orders', {})
            logging.debug(f"Retrieved orders: {orders}")
            if orders:
                # Verify the first order has the required methods for debugging
                first_order = next(iter(orders.values()))
                logging.debug(f"First order attributes: {dir(first_order)}")
            return render_template('orders.html', orders=orders.values()) #renders order page with all orders
    except Exception as e:
        logging.error(f"Error in view_orders: {str(e)}")
        flash("Error viewing orders", "error")
        return redirect(url_for('home'))
                        
@app.route('/order/<order_id>')
def view_order(order_id):
    """View a specific order"""
    try:
        with shelve.open('orders.db', 'r') as db:
            orders = db.get('orders', {}) # Get all orders
            order = orders.get(order_id) # Find specific order
            if order:
                return render_template('order_details.html', order=order, google_maps_api_key=GOOGLE_MAPS_API_KEY)
            flash("Order not found", "error")
    except Exception as e:
        logging.error(f"Error in view_order: {str(e)}", exc_info=True)
        flash("Error retrieving order", "error")
    return redirect(url_for('view_orders'))

@app.route('/order_confirmation/<order_id>') ## just display order dates, duration and ID
def order_confirmation(order_id):
    """Order confirmation page"""
    try:
        with shelve.open('orders.db', 'r') as db:
            orders = db.get('orders', {})
            order = orders.get(order_id)
            if order:
                return render_template('order_confirmation.html', order_id=order_id, order=order, google_maps_api_key=GOOGLE_MAPS_API_KEY)
            flash("Order not found", "error")
    except Exception as e:
        logging.error(f"Error in order_confirmation: {str(e)}", exc_info=True)
        flash("Error retrieving order details", "error")
    return redirect(url_for('home'))

@app.route('/order/<order_id>/edit', methods=['GET', 'POST'])
def edit_order(order_id):
    try:
        with shelve.open('orders.db', 'c') as db:  # Open orders database in write mode
            orders = db.get('orders', {})
            order = orders.get(order_id)
            
            if not order:
                flash("Order not found", "error")
                return redirect(url_for('view_orders'))
            
            if request.method == 'POST':
                try:
                    # Convert string dates to datetime objects
                    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
                    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
                    
                    # Validate date range
                    if start_date > end_date:
                        flash("Start date must be before end date", "error")
                        return render_template('edit_order.html', order=order)
                    
                    # Calculate new duration
                    days = (end_date - start_date).days + 1
                    
                    # Update order details
                    order.rental_dates['start_date'] = request.form['start_date']
                    order.rental_dates['end_date'] = request.form['end_date']
                    order.rental_dates['days'] = days
                    
                    # Get base price - handle both product and bike scenarios
                    first_item = list(order.items.values())[0]
                    if 'product' in first_item:
                        base_price = first_item['product'].get_price()
                    elif 'bike' in first_item:
                        base_price = first_item['bike'].get('price', 0)
                    else:
                        base_price = 0
                    
                    # Update total based on new duration
                    order.total = base_price * days
                    
                    # Save edited order
                    orders[order_id] = order
                    db['orders'] = orders
                    
                    flash("Order updated successfully!", "success")
                    return redirect(url_for('view_order', order_id=order_id))
                
                except Exception as e:
                    logging.error(f"Error processing order edit: {e}")
                    flash("Error updating order details", "error")
                    return render_template('edit_order.html', order=order)
                
            return render_template('edit_order.html', order=order)
    
    except Exception as e:
        logging.error(f"Error accessing orders database for edit: {e}")
        flash("System error occurred", "error")
        return redirect(url_for('view_orders'))
        
@app.route('/order/<order_id>/delete', methods=['POST'])
def delete_order(order_id):
    try:
        with shelve.open('orders.db', 'c') as db:  # write mode
            orders = db.get('orders', {})  # get all orders
            
            if order_id in orders:
                # Optional: Implement soft delete or archiving if needed
                deleted_order = orders.pop(order_id)  # delete order
                db['orders'] = orders
                
                # Optional logging of deleted order
                logging.info(f"Order {order_id} deleted. Original order details: {deleted_order.get_order_id()}")
                
                flash("Order deleted successfully!", "success")
            else:
                flash("Order not found", "error")
            
            return redirect(url_for('view_orders'))
    
    except Exception as e:
        logging.error(f"Error deleting order {order_id}: {e}")
        flash("Error deleting order", "error")
        return redirect(url_for('view_orders'))    

def find_nearest_carpark(latitude, longitude):
    """
    Find the nearest carpark to the given coordinates using a simple distance calculation.
    """
    if not latitude or not longitude:
        return None
        
    def calculate_distance(lat1, lng1, lat2, lng2):
        # Simple Euclidean distance - for more accuracy, you might want to use haversine formula
        return ((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) ** 0.5
    
    nearest_carpark = None
    min_distance = float('inf')
    
    for carpark_id, carpark_data in carparks.items():
        # Since your carpark data is in [name, lat, lng] format
        name = carpark_data[0]
        carpark_lat = carpark_data[1]
        carpark_lng = carpark_data[2]
        
        distance = calculate_distance(
            float(latitude),
            float(longitude),
            carpark_lat,
            carpark_lng
        )
        
        if distance < min_distance:
            min_distance = distance
            nearest_carpark = {
                'id': carpark_id,
                'name': name,
                'distance': distance,
                'coordinates': {'lat': carpark_lat, 'lng': carpark_lng}
            }
    
    return nearest_carpark


@app.route('/manage-ids', methods=['GET', 'POST'])
def manage_ids():
    form = BikeIDManagementForm()
    if form.validate_on_submit():
        try:
            with shelve.open('bike.db', 'c') as bike_db:
                bikes = bike_db.get('Bikes', {})
                bike_name = form.bike_name.data

                # Check if BikeProduct exists, if not, create it
                existing_bike = None
                for bike_data in bikes.values():
                    # Convert dictionary to BikeProduct if necessary
                    if isinstance(bike_data, dict):
                        bike = BikeProduct(
                            bike_name=bike_data.get("bike_name", ""),
                            upload_bike_image=bike_data.get("upload_bike_image", ""),
                            price=bike_data.get("price", 0),
                            transmission_type=bike_data.get("transmission_type", ""),
                            seating_capacity=bike_data.get("seating_capacity", 0),
                            engine_output=bike_data.get("engine_output", 0),
                            stock_quantity=bike_data.get("stock_quantity", 0)
                        )
                    else:
                        bike = bike_data  # Assume it's already a BikeProduct instance

                    if bike.get_bike_name() == bike_name:
                        existing_bike = bike
                        break

                if not existing_bike:
                    new_bike_id = len(bikes) + 1
                    new_bike = BikeProduct(
                        bike_name=bike_name,
                        upload_bike_image="",
                        price=0,
                        transmission_type="",
                        seating_capacity=0,
                        engine_output=0,
                        stock_quantity=form.stock_quantity.data
                    )
                    bikes[new_bike_id] = new_bike
                else:
                    existing_bike.set_stock_quantity(
                        existing_bike.get_stock_quantity() + form.stock_quantity.data
                    )

                bike_db['Bikes'] = bikes

                # Regenerate bike IDs
                initialize_bike_ids(bikes)

                flash('BikeProduct and bike IDs updated successfully!', 'success')
                return redirect(url_for('manage_ids'))

        except Exception as e:
            logging.error(f"Error in manage_ids: {str(e)}")
            flash('Error processing request', 'error')

    if request.method == 'POST' and 'edit_bike_id' in request.form:
        try:
            old_bike_id = request.form.get('old_bike_id')
            new_bike_id = request.form.get('new_bike_id')

            with shelve.open('bike_ids.db', 'c') as db:
                bike_ids = db.get('bike_ids', {})

                if old_bike_id in bike_ids:
                    bike_info = bike_ids.pop(old_bike_id)
                    bike_ids[new_bike_id] = bike_info

                    db['bike_ids'] = bike_ids

                    flash(f"Bike ID updated from {old_bike_id} to {new_bike_id} successfully!", 'success')
                else:
                    flash("Old Bike ID not found.", 'error')

        except Exception as e:
            logging.error(f"Error updating bike ID: {str(e)}")
            flash('Error updating bike ID', 'error')

    try:
        bike_inventory = {}
        with shelve.open('bike_ids.db', 'r') as db:
            bike_ids = db.get('bike_ids', {})

        with shelve.open('bike.db', 'r') as db:
            bikes = db.get('Bikes', {})

        # Debug log: Check retrieved data
        logging.debug(f"Retrieved bike_ids: {bike_ids}")
        logging.debug(f"Retrieved bikes: {bikes}")

        # Build inventory
        for bike_data in bikes.values():
            # Convert dictionary to BikeProduct if necessary
            if isinstance(bike_data, dict):
                bike = BikeProduct(
                    bike_name=bike_data.get("bike_name", ""),
                    upload_bike_image=bike_data.get("upload_bike_image", ""),
                    price=bike_data.get("price", 0),
                    transmission_type=bike_data.get("transmission_type", ""),
                    seating_capacity=bike_data.get("seating_capacity", 0),
                    engine_output=bike_data.get("engine_output", 0),
                    stock_quantity=bike_data.get("stock_quantity", 0)
                )
            else:
                bike = bike_data  # Assume it's already a BikeProduct instance

            bike_name = bike.get_bike_name()
            bike_inventory[bike_name] = {
                'stock': bike.get_stock_quantity(),
                'rental': bike.get_rental(),
                'ids': {
                    bike_id: {**bike_info, 'id': bike_id}
                    for bike_id, bike_info in bike_ids.items()
                    if bike_info['name'] == bike_name
                }
            }

        # Debug log: Check bike inventory after processing
        logging.debug(f"Built bike_inventory: {bike_inventory}")

    except Exception as e:
        bike_inventory = {}
        logging.error(f"Error retrieving bike IDs and products: {e}")

    return render_template('manage_ids.html', form=form, bike_inventory=bike_inventory)


@app.route('/delete-id/<id_string>', methods=['POST'])
def delete_id(id_string):
    try:
        # Instead of deleting bike ID, reset its status
        with shelve.open('bike_ids.db', 'c') as db:
            bike_ids = db.get('bike_ids', {})
            if id_string in bike_ids:
                bike_ids[id_string]['status'] = 'available'
                bike_ids[id_string]['current_user'] = None
                db['bike_ids'] = bike_ids
                flash('Bike ID reset successfully!', 'success')
            else:
                flash('Bike ID not found', 'error')
    except Exception as e:
        logging.error(f"Error in delete_id: {str(e)}")
        flash('Error processing request', 'error')

    return redirect(url_for('manage_ids'))


@app.route('/unlock', methods=['GET', 'POST'])
def unlock_bike():
    form = LockUnlockForm()
    if form.validate_on_submit():
        try:
            bike_id = form.bike_id.data.upper()
            user_email = session.get('user_email')

            if not user_email:
                flash('Please create an order first', 'error')
                return render_template('unlock.html', form=form)

            # Get bike ID data
            with shelve.open('bike_ids.db', 'c') as db:
                bike_ids = db.get('bike_ids', {})
                if bike_id not in bike_ids:
                    flash('Invalid bike ID', 'error')
                    return render_template('unlock.html', form=form)

                bike_info = bike_ids[bike_id]
                bike_name = bike_info['name']

            # Get bike data and check stock
            with shelve.open('bike.db', 'c') as db:
                bikes = db.get('Bikes', {})
                bike = None
                for b in bikes.values():
                    if b.get_bike_name() == bike_name:
                        bike = b
                        break

                if not bike:
                    flash('Bike not found', 'error')
                    return render_template('unlock.html', form=form)

                if bike.get_stock_quantity() <= 0:
                    flash('No bikes available for this model', 'error')
                    return render_template('unlock.html', form=form)

            # Verify rental status
            with shelve.open('orders.db', 'r') as db:
                orders = db.get('orders', {})
                has_valid_rental = False
                for order in orders.values():
                    if (
                        order.get_customer_info()['email'] == user_email
                        and any(
                            item['bike'].get_bike_name() == bike_name
                            for item in order.get_items().values()
                        )
                    ):
                        has_valid_rental = True
                        break

                if not has_valid_rental:
                    flash('No active rental found for this bike', 'error')
                    return render_template('unlock.html', form=form)

            # Process unlock
            if bike_info['status'] == 'unlocked':
                flash('Bike is already unlocked', 'error')
                return render_template('unlock.html', form=form)

            # Update bike status
            with shelve.open('bike_ids.db', 'c') as db:
                bike_ids = db.get('bike_ids', {})
                bike_ids[bike_id]['status'] = 'unlocked'
                bike_ids[bike_id]['current_user'] = user_email
                db['bike_ids'] = bike_ids

            # Update bike stock and rental count
            with shelve.open('bike.db', 'c') as db:
                bikes = db.get('Bikes', {})
                for b in bikes.values():
                    if b.get_bike_name() == bike_name:
                        b.increase_rental()
                        break
                db['Bikes'] = bikes

            flash('Bike unlocked successfully!', 'success')
            return redirect(url_for('lock_success'))

        except Exception as e:
            logging.error(f"Error in unlock_bike: {str(e)}")
            flash('Error processing request', 'error')

    return render_template('unlock.html', form=form)

@app.route('/lock-success')
def lock_success():
    return render_template('lock_success.html')


def initialize_orders():
    """Initialize the orders database if it doesn't exist"""
    try:
        with shelve.open('orders.db', 'c') as db:
            if 'orders' not in db:
                db['orders'] = {}
            logging.info("Orders database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing orders database: {e}")

def initialize_bike_ids(products):
    """Initialize bike IDs based on existing products"""
    try:
        with shelve.open('bike_ids.db', 'c') as db:
            bike_ids = {}
            for idx, product_data in enumerate(products.values(), 1):
                # Convert dictionary to BikeProduct if necessary
                if isinstance(product_data, dict):
                    product = BikeProduct(
                        bike_name=product_data.get("bike_name", ""),
                        upload_bike_image=product_data.get("upload_bike_image", ""),
                        price=product_data.get("price", 0),
                        transmission_type=product_data.get("transmission_type", ""),
                        seating_capacity=product_data.get("seating_capacity", 0),
                        engine_output=product_data.get("engine_output", 0),
                        stock_quantity=product_data.get("stock_quantity", 0)
                    )
                else:
                    product = product_data  # Already a BikeProduct instance

                # Generate bike IDs based on product order
                bike_id = f"BIKE{idx:03d}"
                bike_ids[bike_id] = {
                    'name': product.get_bike_name(),
                    'status': 'available',
                    'current_user': None
                }

            db['bike_ids'] = bike_ids
            logging.info("Bike IDs database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing bike IDs database: {e}")

        
@app.route('/check-session')
def check_session():
    email = session.get('user_email')
    return f"Current email in session: {email}"

# Add this to your if __name__ == '__main__': block
if __name__ == '__main__':
    initialize_orders()
    
    # Load products first before initializing bike IDs
    with shelve.open('product.db', 'r') as db:
        products = db.get('products', {})
        initialize_bike_ids(products)
    
    app.run(debug=True)
