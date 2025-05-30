from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify
from flask_mail import Mail, Message
from flask_caching import Cache
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import db
from database.models import SearchResult, save_results_to_db, User, Application
from optimization.resume import resume_text, resume_keywords, optimize_resume
from apscheduler.schedulers.background import BackgroundScheduler
from crawler.crawler import LinkedInScraper, GoogleScraper, TemporaryScraper
import os
from werkzeug.utils import secure_filename
import uuid
from PIL import Image, ImageDraw
from sqlalchemy.orm import joinedload



#* App
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

migrate = Migrate(app, db)

app.secret_key = os.environ.get('SECRET_KEY')

@app.before_first_request
def create_tables():
    db.create_all()

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
PROFILE_PIC = 'vantage/static/profile_uploads'
os.makedirs('static/profile_uploads', exist_ok=True)
app.config['PROFILE_PIC'] = PROFILE_PIC
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'profile_uploads')

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
    results = SearchResult.query.order_by(SearchResult.id.desc()).limit(15).all() #! Should update everytime the crawler is automatically used
    user = None
    if 'user_id' not in session:
        return render_template('sohome.html', results=results, user=user)
    else:
        user = User.query.get(session['user_id']) 

        mini_apps = []
        if user:
            mini_apps = sorted(user.applications, key=lambda a: a.applied_at, reverse=True)[:3]
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

            user = User.query.filter_by(username=username).first()
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

            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                error = 'Username Taken'
                return render_template('auth.html', error=error, form_type='register')
            
            hashed_password = generate_password_hash(password, method='scrypt')
            new_user = User(
                first_name=first_name,
                last_name=last_name,
                username=username, 
                password=hashed_password,
                email=email,
                degree=degree,
                address=address
                )
            db.session.add(new_user)
            db.session.commit()
            session['username'] = new_user.username
            session['user_id'] = new_user.id

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

    user = User.query.get(session['user_id'])
    if user:
        return render_template('profile.html', user=user)
    else:
        redirect(url_for('login'))

@app.route('/edit_profile', methods=['POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user:
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.email = request.form['email']
        user.degree = request.form['degree']
        user.address = request.form['address']
        user.username = request.form['username']

        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
                file.save(temp_path)

                cropped_filename = circular_crop(temp_path)
                user.profile_pic = cropped_filename

                try:
                    os.remove(temp_path)
                except Exception:
                        pass

        db.session.commit()
        edit_message = "Profile updated successfully."
        return redirect(url_for('profile', edit_message=edit_message))
    else:
        return "User not found", 404

@app.route('/upload_cropped_image', methods=['POST'])
def upload_cropped_image():
    if 'user_id' not in session:
        return jsonify({"message": "Not logged in"}), 401

    user = User.query.get(session['user_id'])
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
    user = User.query.get(session['user_id'])
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
    user = User.query.filter_by(username=username).first()
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

#* Search
    
    #! Cache search results for set time
    #! Add location search feature
    #! Save to database only if user applies to the job (save to application table)

    #! Fix filter dropdown closing before applying selection

@app.route('/search', methods=['GET', 'POST'])
def search():

    page = int(request.args.get('page', 1))
    per_page = 10

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
    else:
        query = request.args.get('query', '').strip()

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
            'key': 'AIzaSyB4m72GwM1JZRE6axO2b7DHIGyK_DaFBc4',
            'cx': 'd0f5dd3892bd54768',
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
        query_filter = (SearchResult.job.ilike(f"%{query}%")) | \
                    (SearchResult.company.ilike(f"%{query}%")) | \
                    (SearchResult.location.ilike(f"%{query}%"))

        q = SearchResult.query.filter(query_filter)

        if not show_companies:
            q = q.filter((SearchResult.company == None) | (SearchResult.company == ""))

        if show_requirements:
            q = q.filter(SearchResult.requirements != None).filter(SearchResult.requirements != "")

        if show_ideal:
            q = q.filter(SearchResult.ideal_path != None).filter(SearchResult.ideal_path != "")
       
        pagination = q.distinct().paginate(page=page, per_page=per_page, error_out=False)
        db_results = pagination.items
        total_db_results = pagination.total

    # Cache results
    cache.set(cache_key, {
        'db_results': [serialize_result(r) for r in db_results],
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
        user=User.query.get(session['user_id']) if 'user_id' in session else None,
        page=page,
        total_db_results=total_db_results,
        per_page=per_page,
        pagination=pagination,
        show_db=show_db,
        show_companies=show_companies,
        show_requirements=show_requirements,
        show_ideal=show_ideal
    )
    linked_results = []
    if query:
        linked_results = TemporaryScraper.temporary_search(query)

    unique_results = []
    seen = set()

    for r in db_results:
        identifier = (r.job, r.company, r.location)  # Or any fields that define uniqueness
        if identifier not in seen:
            seen.add(identifier)
            unique_results.append(r)


    def serialize_result(result):
        return {
            'id': result.id,
            'job': result.job,
            'company': result.company,
            'location': result.location,
            'description': getattr(result, 'description', None),
            'snippet': getattr(result, 'snippet', ''),
            'url': getattr(result, 'url', None),
        }



    return render_template(
        'search.html',
    )    

@app.route('/posting/<int:result_id>')
def posting(result_id):
    user = User.query.get(session['user_id']) if 'user_id' in session else None

    posting = SearchResult.query.get_or_404(result_id)

    similar_postings = SearchResult.query.filter(
        (SearchResult.company == posting.company) |
        (SearchResult.job.ilike(f"%{posting.job}%"))
    ).filter(SearchResult.id != posting.id).limit(5).all()

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
        return "Posting not found", 404
    result = linked_results[result_index]
    user = User.query.get(session['user_id']) if 'user_id' in session else None

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
    user = User.query.get(session['user_id']) if 'user_id' in session else None

    return render_template(
        'posting.html',
        posting=result,
        prev_query=query,
        user=user,
        similar_postings=[] 
    )

@app.route('/save_result', methods=['POST'])
def save_result():
    job = request.form['job']
    company = request.form['company']
    location = request.form['location']
    description = request.form['description']
    url = request.form['url']
    # Add any other fields you want

    new_result = SearchResult(
        job=job,
        company=company,
        location=location,
        description=description,
        url=url
    )
    db.session.add(new_result)
    db.session.commit()
    return redirect(url_for('search', query=job))

#* Message

@app.route('/message', methods=['GET', 'POST'])
def message():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        recipient_username = request.form['recipient']
        content = request.form['content']
        recipient = User.query.filter_by(username=recipient_username).first()
        if recipient and content.strip():
            msg = Message(sender_id=user.id, recipient_id=recipient.id, content=content)
            db.session.add(msg)
            db.session.commit()

    conversation_user_ids = set(
        [m.sender_id for m in user.received_messages] +
        [m.recipient_id for m in user.sent_messages]
    )
    conversation_user_ids.discard(user.id)
    all_conversation_users = User.query.filter(User.id.in_(conversation_user_ids)).all()
    user_conversations = [u for u in all_conversation_users if not getattr(u, 'is_company', False)]
    company_conversations = [u for u in all_conversation_users if getattr(u, 'is_company', False)]

    selected_username = request.args.get('with')
    selected_user = None
    messages = []
    if selected_username:
        selected_user = User.query.filter_by(username=selected_username).first()
        if selected_user:
            messages = Message.query.filter(
                ((Message.sender_id == user.id) & (Message.recipient_id == selected_user.id)) |
                ((Message.sender_id == selected_user.id) & (Message.recipient_id == user.id))
            ).order_by(Message.timestamp.asc()).all()

    return render_template(
        'message.html',
        user=user,
        user_conversations=user_conversations,
        company_conversations=company_conversations,
        selected_user=selected_user,
        messages=messages
    )

#* Application

@app.route('/application', methods=['GET', 'POST'])
def application():
    try:
        if'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])

        active_statuses = ['Applied', 'Interview', 'Offer']
        inactive_statuses = ['Rejected', 'Withdrawn', 'Closed']

        active_apps = [app for app in user.applications if app.status in active_statuses]
        inactive_apps = [app for app in user.applications if app.status in inactive_statuses]
        return render_template('application.html', user=user, active_apps=active_apps, inactive_apps=inactive_apps)

    except Exception as e:
        app.logger.error(f'Error in /application route: {e}')
        return 'An error occured'

@app.route('/apply/<int:result_id>', methods=['POST'])
def apply(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or not user.resume_filename:
        return "No resume", redirect(url_for('upload_resume'))
    
    resume_txt = resume_text(user.username)
    internship = SearchResult.query.get(result_id)
    if not internship:
        return "Internship not found", 404
    
    application = Application(user_id=user.id, job_id=internship.id, status='Applied')
    db.session.add(application)
    db.session.commit()

    internship_description = internship.description or ""
    if not internship_description:
        return "Internship description not available", 404

    common_words, match_percent = optimize_resume(resume_txt, internship_description)

    return render_template(
        'apply.html',
        common_words=common_words,
        match_percent=match_percent,
        internship=internship,
        user=user
    )

@app.route('/apply_linkedin', methods=['POST'])
def apply_linkedin():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    # Save the posting to SearchResult if not already saved
    job = request.form['title']
    company = request.form['company']
    location = request.form['location']
    description = request.form['description']
    url = request.form['url']
    # Check if already exists
    existing = SearchResult.query.filter_by(job=job, company=company, url=url).first()
    if not existing:
        new_result = SearchResult(
            job=job,
            company=company,
            location=location,
            description=description,
            url=url
        )
        db.session.add(new_result)
        db.session.commit()
        result_id = new_result.id
    else:
        result_id = existing.id
    # Create application
    application = Application(user_id=user.id, job_id=result_id, status='Applied')
    db.session.add(application)
    db.session.commit()
    return redirect(url_for('application'))

#* History

@app.route('/history', methods=['GET', 'POST'])
def history():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user_id = session['user_id']        
        user = User.query.filter_by(id=user_id).first()

        if not user:
            return 'User not found', 404
        
        return render_template('history.html', user=user)
    except Exception as e:
        app.logger.error(f'Error in /message route: {e}')
        return 'An error occured while fetching messages'


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)