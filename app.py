from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify, flash
from flask_mail import Mail, Message
from flask_caching import Cache
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from crawler.crawler import LinkedInScraper, GoogleScraper, TemporaryScraper
import os
from werkzeug.utils import secure_filename
import uuid
from PIL import Image, ImageDraw
from sqlalchemy.orm import joinedload
from database.db import users, applications, search_results, messages, saved_listings
from bson import ObjectId
from datetime import datetime


#* App
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.secret_key = 'anythin'

#* DB


#* Cache
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 300

cache = Cache(app)

#* Password Reset
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

s = URLSafeTimedSerializer(app.secret_key)

#* Profile Pic
PROFILE_PIC = os.path.join('static', 'profile_uploads')
os.makedirs('static/profile_uploads', exist_ok=True)
app.config['PROFILE_PIC'] = PROFILE_PIC
app.config['UPLOAD_FOLDER'] = PROFILE_PIC

#* Scheduler
scheduler = BackgroundScheduler()

def scrape_and_save_linkedin_jobs():
    with app.app_context():
        scraper = LinkedInScraper()
        results = scraper.scrape_jobs()
        save_results_to_db(results)

def scrape_and_save_google_jobs():
    with app.app_context():
        scraper = GoogleScraper()
        results = scraper.scrape_jobs()
        save_results_to_db(results)

# Schedule the scraping jobs
scheduler.add_job(scrape_and_save_linkedin_jobs, 'interval', hours=1, id='linkedin_scrape_job', replace_existing=True)
scheduler.add_job(scrape_and_save_google_jobs, 'interval', hours=1, id='google_scrape_job', replace_existing=True)
scheduler.start()

def circular_crop(image_path):
    img = Image.open(image_path).convert("RGBA")
    size = min(img.size)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    cropped_img = img.crop(((img.width - size) // 2,
                            (img.height - size) // 2,
                            (img.width + size) // 2,
                            (img.height + size) // 2))
    cropped_img.putalpha(mask)

    output_filename = f"{uuid.uuid4().hex}.png"
    output_path = os.path.join(app.config['PROFILE_PIC'], output_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cropped_img.save(output_path)
    return output_filename

#* Resume/Cover Letter
RESUME_FOLDER = os.path.join(app.root_path, 'ifro', 'optimization', 'resume_uploads')
os.makedirs(RESUME_FOLDER, exist_ok=True)
app.config['RESUME_FOLDER'] = RESUME_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

@app.context_processor
def inject_logged_in():
    return dict(logged_in=('user_id' in session))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#* Home Page

@app.route('/', methods=['GET'])
def home():
    query = "college"
    results = TemporaryScraper.temporary_search(query, max_results=15)

    if 'user_id' not in session:
        return render_template('sohome.html', results=results, user=None)

    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user:
        return render_template('sohome.html', results=results, user=None)

    user_apps = list(applications.find({"user_id": user['_id']}))

    for app in user_apps:
        job = search_results.find_one({"_id": app['job_id']})
        if job:
            app['job_title'] = job.get('title') or job.get('job') or "No Title"
            app['company'] = job.get('company') or "No Company"
        else:
            app['job_title'] = "Unknown Job"
            app['company'] = "Unknown Company"

    mini_apps = sorted(user_apps, key=lambda a: a.get("applied_at", ""), reverse=True)[:3]

    return render_template('sihome.html', results=results, user=user, mini_apps=mini_apps)
    
#* Login Settings

@app.route('/auth', methods=['GET', 'POST'])
def login():

    form_type = 'login'
    if request.method == 'POST':
        form_type = request.form.get('form_type')


        if form_type == 'login':
            # Logic for login
            username = request.form['username']
            password = request.form['password']

            user = users.find_one({'username': username})
            if user and check_password_hash(user.password, password):
                session["username"] = user.username
                session['user_id'] = user.id
                return redirect(url_for('home'))
            else:
                error = 'Invalid username or password'
                return render_template('auth.html', error=error, form_type='login') #* Currently it is not displaying error message

        elif form_type == 'register':
            username = request.form['username']
            password = request.form['password'] #! Password should meet a certain criteria ie special character, length, numbers
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            email = request.form['email']
            degree = request.form['degree']
            address = request.form['address']

            existing_user = users.find_one({"username": username})
            if existing_user:
                error = 'Username Taken'
                return render_template('auth.html', error=error, form_type='register')
            hashed_password = generate_password_hash(password, method='scrypt')
            new_user = {
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "password": hashed_password,
                "email": email,
                "degree": degree,
                "address": address
            }
            users.insert_one(new_user)
            session['username'] = username
            session['user_id'] = str(new_user["_id"])

            return redirect(url_for('profile'))
        
    return render_template('auth.html', form_type=form_type)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

#* Password Settings

@app.route('/change_password', methods=['POST'])
def change_password():          #! Fix the style of page
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    if not check_password_hash(user.password, current_password):
        password_message = "Current password is incorrect."
    elif new_password != confirm_password:
        password_message = "New passwords do not match."
    else:
        user.password = generate_password_hash(new_password)
        db.session.commit()
        password_message = "Password changed successfully."
    # Render profile page with message (ensure you pass password_message to template)
    return redirect(url_for('profile', password_message=password_message))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():      #! Fix style of page
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = s.dumps(user.email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request',
                          sender=app.config['MAIL_USERNAME'],
                          recipients=[user.email])
            msg.body = f'Click the link to reset your password: {reset_url}'
            mail.send(msg)
            message = "Password reset instructions sent to your email."
        else:
            message = "Email not found."
        return render_template('forgot_password.html', message=message)
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):      #! Fix style of page
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600)  # 1 hour expiration
    except Exception:
        return "The reset link is invalid or has expired."
    if request.method == 'POST':
        new_password = request.form['new_password']
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('reset_password.html')

#* User Profile

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if'user_id' not in session:
        return redirect(url_for('login'))

    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if user:
        return render_template('profile.html', user=user)
    else:
        redirect(url_for('login'))

@app.route('/edit_profile', methods=['POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    update_fields = {
        "first_name": request.form.get('first_name'),
        "last_name": request.form.get('last_name'),
        "email": request.form.get('email'),
        "degree": request.form.get('degree'),
        "address": request.form.get('address'),
        "username": request.form.get('username'),
    }
    
    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
            file.save(temp_path)

            cropped_filename = circular_crop(temp_path)
            update_fields['profile_pic'] = cropped_filename

            try:
                os.remove(temp_path)
            except Exception:
                pass

    update_fields = {k: v for k, v in update_fields.items() if v is not None}

    result = users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        return "User not found", 404

    return redirect(url_for('profile'))

@app.route('/upload_cropped_image', methods=['POST'])
def upload_cropped_image():
    if 'user_id' not in session:
        return jsonify({"message": "Not logged in"}), 401

    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user:
        return jsonify({"message": "User not found"}), 404

    file = request.files.get('profile_pic')
    if not file:
        return jsonify({"message": "No image provided"}), 400

    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    upload_path = os.path.join('static', 'profile_uploads', unique_filename)
    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
    file.save(upload_path)

    user.profile_pic = unique_filename
    db.session.commit()

    return jsonify({"message": "Profile picture updated successfully."})
    
@app.route('/upload_resume', methods=['GET', 'POST'])
def upload_resume():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if request.method == 'POST':
        if 'resume' not in request.files:
            return "No file part", 400
        file = request.files['resume']
        if file.filename == '':
            return "No selected file", 400
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{user.username}_resume.pdf")
            file.save(os.path.join(app.config['RESUME_FOLDER'], filename))
            user.resume_filename = filename
            db.session.commit()
            return redirect(url_for('profile', tab='resume'))
        else:
            return "Invalid file type. Only PDF allowed.", 400
    return render_template('upload_resume.html')

@app.route('/resume/<username>')
def view_resume(username):
    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user or not user.resume_filename:
        return "Resume not found.", 404

    resume_path = os.path.join(app.config['RESUME_FOLDER'], user.resume_filename)
    if not os.path.exists(resume_path):
        return "Resume file missing", 404            
    else:
        return send_from_directory(
            app.config['RESUME_FOLDER'],
            user.resume_filename,
            as_attachment=False)

# Search

@app.route('/search', methods=['GET', 'POST'])
def search():
    page = int(request.args.get('page', 1))
    per_page = 10

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
    else:
        query = request.args.get('query', '').strip()
    if not query:
        query = "college internships"

    show_db = request.values.get('show_db', '1') == '1'
    show_companies = request.values.get('show_companies', '1') == '1'
    show_requirements = request.values.get('show_requirements', '1') == '1'
    show_ideal = request.values.get('show_ideal', '1') == '1'

    force_refresh = request.values.get('refresh', '0') == '1'
    cache_key = f"search:{query}:{page}:{show_db}:{show_companies}:{show_requirements}:{show_ideal}"

    linked_results = TemporaryScraper.temporary_search(query) if query else []
    google_results = GoogleScraper.search_api(
        user_query=f"{query} internship",
        total_results=per_page,
        params={
            'key': 'AIzaSyDq_GFJzlkOQV0R0EFBD8iVdyCvqypLbk4',
            'cx': 'f43b15d72db4d49d3',
            'q': query,
            'start': 1 + (page - 1) * per_page
        },
        url='https://customsearch.googleapis.com/customsearch/v1',
        ignore_keywords=['linkedin', 'indeed', 'wikipedia'],
        results_per_page=per_page
    ) if query else []

    seen_links = set()
    unique_google_results = []
    for result in google_results:
        link = result.get('link')
        if link in seen_links:
            continue
        seen_links.add(link)
        unique_google_results.append(result)
    google_results = unique_google_results    

    db_results = []
    total_db_results = 0
    pagination = None
    if show_db and query:
        mongo_filter = {
            "$or": [
                {"job": {"$regex": query, "$options": "i"}},
                {"company": {"$regex": query, "$options": "i"}},
                {"location": {"$regex": query, "$options": "i"}}
            ]
        }
        if not show_companies:
            mongo_filter["company"] = {"$in": [None, ""]}
        if show_requirements:
            mongo_filter["requirements"] = {"$ne": None, "$ne": ""}
        if show_ideal:
            mongo_filter["ideal_path"] = {"$ne": None, "$ne": ""}

        total_db_results = search_results.count_documents(mongo_filter)
        db_results = list(
            search_results.find(mongo_filter)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )

    class Pagination:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=2, left_current=2, right_current=2, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge or
                    (num >= self.page - left_current and num <= self.page + right_current) or
                    num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    # Cache results
    cache.set(cache_key, {
        'db_results': db_results,
        'google_results': google_results,
        'linked_results': linked_results,
        'total_db_results': total_db_results,
    })

    return render_template(
        'search.html',
        db_results=db_results,
        google_results=google_results,
        linked_results=linked_results,
        query=query,
        user=users.find_one({"_id": ObjectId(session['user_id'])}) if 'user_id' in session else None,
        page=page,
        total_db_results=total_db_results,
        per_page=per_page,
        pagination=pagination,
        show_db=show_db,
        show_companies=show_companies,
        show_requirements=show_requirements,
        show_ideal=show_ideal
    )   

@app.route('/posting/<result_id>')
def posting(result_id):
    user = users.find_one({"_id": ObjectId(session['user_id'])}) if 'user_id' in session else None

    posting = search_results.find_one({"_id": ObjectId(result_id)})
    if not posting:
        return "Posting not found", 404

    # Find similar postings (by company or similar job title, excluding current posting)
    similar_postings = list(
        search_results.find({
            "$and": [
                {"_id": {"$ne": ObjectId(result_id)}},
                {"$or": [
                    {"company": posting.get("company")},
                    {"job": {"$regex": posting.get("job", ""), "$options": "i"}}
                ]}
            ]
        }).limit(5)
    )

    return render_template(
        'posting.html',
        posting=posting,
        prev_query=request.args.get('query', ''),
        user=user,
        similar_postings=similar_postings
    )

@app.route('/linkedin_posting/<int:result_index>')
def linkedin_posting(result_index):
    query = request.args.get('query', '')
    page = int(request.args.get('page', 1))
    show_db = request.args.get('show_db', '1')
    show_companies = request.args.get('show_companies', '1')
    show_requirements = request.args.get('show_requirements', '1')
    show_ideal = request.args.get('show_ideal', '1')

    cache_key = f"search:{query}:{page}:{show_db}:{show_companies}:{show_requirements}:{show_ideal}"
    cached = cache.get(cache_key)
    linked_results = cached.get('linked_results', []) if cached else []

    if not linked_results or result_index >= len(linked_results):
        flash("LinkedIn posting not found or expired.", "danger")
        return redirect(url_for('search', query=query, page=page))

    result = linked_results[result_index]

    user = None
    if 'user_id' in session:
        try:
            user = users.find_one({"_id": ObjectId(session['user_id'])})
        except:
            user = None

    return render_template(
        'linkedin_posting.html',
        posting=result,
        user=user,
        prev_query=query,
        page=page,
        show_db=show_db,
        show_companies=show_companies,
        show_requirements=show_requirements,
        show_ideal=show_ideal
    )

@app.route('/google_posting/<int:result_index>')
def google_posting(result_index):
    query = request.args.get('query', '')
    page = int(request.args.get('page', 1))
    show_db = request.args.get('show_db', '1')
    show_companies = request.args.get('show_companies', '1')
    show_requirements = request.args.get('show_requirements', '1')
    show_ideal = request.args.get('show_ideal', '1')
    cache_key = f"search:{query}:{page}:{show_db}:{show_companies}:{show_requirements}:{show_ideal}"

    cached = cache.get(cache_key)
    if not cached or result_index >= len(cached['google_results']):
        return "Posting not found", 404

    result = cached['google_results'][result_index]
    user = users.find_one({"_id": ObjectId(session['user_id'])}) if 'user_id' in session else None

    return render_template(
        'google_posting.html',  # changed from 'posting.html'
        posting=result,
        prev_query=query,
        user=user,
        page=page,
        show_db=show_db,
        show_companies=show_companies,
        show_requirements=show_requirements,
        show_ideal=show_ideal
    )

@app.route('/save_result', methods=['POST'])
def save_result():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    job = request.form['job']
    company = request.form['company']
    location = request.form['location']
    description = request.form['description']
    url = request.form['url']

    # Check if the result already exists in the DB
    result = search_results.find_one({"job": job, "company": company, "url": url})
    if not result:
        result_data = {
            "job": job,
            "company": company,
            "location": location,
            "description": description,
            "url": url
        }
        insert_result = search_results.insert_one(result_data)
        result_id = insert_result.inserted_id
    else:
        result_id = result["_id"]

    # Check if already saved
    existing_saved = saved_listings.find_one({"user_id": user_id, "job_id": result_id})
    if not existing_saved:
        saved = {
            "user_id": user_id,
            "job_id": result_id
        }
        saved_listings.insert_one(saved)

    return redirect(url_for('search', query=job))

#* Message

@app.route('/message', methods=['GET', 'POST'])
def message():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_username = request.form['recipient']
        content = request.form['content']
        recipient = users.find_one({"username": recipient_username})
        if recipient and content.strip():
            msg_doc = {
                "sender_id": user["_id"],
                "recipient_id": recipient["_id"],
                "content": content,
                "timestamp": datetime.utcnow()
            }
            messages.insert_one(msg_doc)

    sent_msgs = messages.find({"sender_id": user["_id"]})
    recv_msgs = messages.find({"recipient_id": user["_id"]})

    conversation_user_ids = set()
    for m in sent_msgs:
        conversation_user_ids.add(m["recipient_id"])
    for m in recv_msgs:
        conversation_user_ids.add(m["sender_id"])

    conversation_user_ids.discard(user["_id"])

    conversation_users = list(users.find({"_id": {"$in": list(conversation_user_ids)}}))

    user_conversations = [u for u in conversation_users if not u.get("is_company", False)]
    company_conversations = [u for u in conversation_users if u.get("is_company", False)]

    selected_username = request.args.get('with')
    selected_user = None
    convo_messages = []
    if selected_username:
        selected_user = users.find_one({"username": selected_username})
        if selected_user:
            convo_messages = list(messages.find({
                "$or": [
                    {"sender_id": user["_id"], "recipient_id": selected_user["_id"]},
                    {"sender_id": selected_user["_id"], "recipient_id": user["_id"]}
                ]
            }).sort("timestamp", 1))

    return render_template(
        'message.html',
        user=user,
        user_conversations=user_conversations,
        company_conversations=company_conversations,
        selected_user=selected_user,
        messages=convo_messages
    )

#* Application

@app.route('/application')
def application():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = ObjectId(session['user_id'])

    # MongoDB aggregation to join applications and jobs
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$lookup": {
            "from": "search_results",
            "localField": "job_id",
            "foreignField": "_id",
            "as": "job"
        }},
        {"$unwind": "$job"},
        {"$sort": {"applied_at": -1}}
    ]

    apps = list(applications.aggregate(pipeline))

    active_statuses = ['Applied', 'Interview', 'Offer']
    inactive_statuses = ['Rejected', 'Withdrawn', 'Closed']

    active_apps = [a for a in apps if a.get("status") in active_statuses]
    inactive_apps = [a for a in apps if a.get("status") in inactive_statuses]

    user = users.find_one({"_id": user_id})

    return render_template("application.html", user=user, active_apps=active_apps, inactive_apps=inactive_apps)

@app.route('/apply/<string:result_id>', methods=['POST'])
def apply(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user:
        return redirect(url_for('login'))

    if 'resume_filename' not in user:
        return redirect(url_for('upload_resume'))

    try:
        internship = search_results.find_one({"_id": ObjectId(result_id)})
    except:
        return "Invalid internship ID", 400

    if not internship:
        return "Internship not found", 404

    resume_txt = resume_text(user["username"])

    internship_description = internship.get("description", "")
    if not internship_description:
        return "Internship description not available", 404

    applications.insert_one({
        "user_id": user["_id"],
        "job_id": internship["_id"],
        "title": internship.get("job", "Internship"),
        "company": internship.get("company", "Unknown"),
        "applied_at": datetime.utcnow(),
        "status": "Applied"
    })

    common_words, match_percent = optimize_resume(resume_txt, internship_description)

    return render_template(
        'apply.html',
        common_words=common_words,
        match_percent=match_percent,
        internship=internship,
        user=user
    )

@app.route('/apply_posting', methods=['POST'])
def apply_posting():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users.find_one({"_id": ObjectId(session['user_id'])})
    if not user:
        return redirect(url_for('login'))

    job = request.form['title']
    company = request.form['company']
    location = request.form['location']
    description = request.form['description']
    url = request.form['url']

    existing = search_results.find_one({
        "job": job,
        "company": company,
        "url": url
    })

    if not existing:
        result_id = search_results.insert_one({
            "job": job,
            "company": company,
            "location": location,
            "description": description,
            "url": url
        }).inserted_id
    else:
        result_id = existing["_id"]

    applications.insert_one({
        "user_id": user["_id"],
        "job_id": result_id,
        "status": "Applied",
        "applied_at": datetime.utcnow()
    })

    return redirect(url_for('application'))

#* Saved

@app.route('/saved', methods=['GET', 'POST'])
def saved():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user_id = ObjectId(session['user_id'])        
        user = users.find_one({"_id": user_id})

        if not user:
            return 'User not found', 404

        saved_docs = list(saved_listings.find({"user_id": user_id}))

        job_ids = [doc.get("job_id") for doc in saved_docs if doc.get("job_id")]

        saved_results = list(search_results.find({"_id": {"$in": job_ids}}))

        return render_template('saved.html', user=user, saved_results=saved_results)

    except Exception as e:
        app.logger.error(f'Error in /saved route: {e}')
        return 'An error occurred while fetching saved listings'

if __name__ == '__main__':
    app.run(debug=True)