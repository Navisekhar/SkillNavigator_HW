from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from bson import ObjectId
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
bcrypt = Bcrypt(app)

# MongoDB Atlas Setup using environment variable
mongodb_uri = os.getenv("MONGO_URI")
client = MongoClient(mongodb_uri)
candidate_db = client['skillnavigator']['candidate']
admin_db = client['skillnavigator']['admin']
# Configure Google Generative AI
genai.configure(api_key=os.getenv("GOOGLE_GEN_AI_API_KEY"))

@app.route('/')
def landing():
    return render_template('landing.html')  # Landing page with buttons for signup and login

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        candidate_db.insert_one({'username': username, 'email': email, 'password': password})
        flash('Signup successful. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        candidate = candidate_db.find_one({'email': email})
        admin = admin_db.find_one({'email': email})

        if candidate and bcrypt.check_password_hash(candidate['password'], password):
            session['user_id'] = str(candidate['_id'])
            session['user_type'] = 'candidate'
            return redirect(url_for('candidate_dashboard'))
        elif admin and bcrypt.check_password_hash(admin['password'], password):
            session['user_id'] = str(admin['_id'])
            session['user_type'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/candidate_dashboard')
def candidate_dashboard():
    if 'user_id' in session and session['user_type'] == 'candidate':
        user = candidate_db.find_one({'_id': ObjectId(session['user_id'])})
        return render_template('candidate_dashboard.html', user=user)
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' in session and session['user_type'] == 'admin':
        candidates = list(candidate_db.find())
        batch_counts = {
            "java_batch": candidate_db.count_documents({"batch": "java"}),
            "data_engineer": candidate_db.count_documents({"batch": "data engineer"}),
            ".net": candidate_db.count_documents({"batch": ".net"})
        }
        return render_template('admin_dashboard.html', candidates=candidates, batch_counts=batch_counts)
    return redirect(url_for('login'))

@app.route('/candidate_info', methods=['GET', 'POST'])
def candidate_info():
    if 'user_id' in session and session['user_type'] == 'candidate':
        if request.method == 'POST':
            candidate_info = {
                "name": request.form['name'],
                "email": request.form['email'],
                "degree": request.form['degree'],
                "specialization": request.form['specialization'],
                "phone": request.form['phone'],
                "certifications": request.form['certifications'],
                "internship_details": request.form['internship_details'],
                "courses_completed": request.form['courses_completed'],
                "linkedin": request.form['linkedin'],
                "github": request.form['github'],
                "languages": request.form['languages'],
                "resume": request.form['resume']
            }
            candidate_db.update_one({'_id': ObjectId(session['user_id'])}, {'$set': candidate_info})
            flash('Information saved successfully.', 'success')
            return redirect(url_for('candidate_dashboard'))
        return render_template('candidate_info.html')
    return redirect(url_for('login'))

@app.route('/batch_allocation')
def batch_allocation():
    if 'user_id' in session and session['user_type'] == 'candidate':
        user = candidate_db.find_one({'_id': ObjectId(session['user_id'])})
        batch = None
        if user.get('certifications') == "Java and AWS":
            batch = "java batch"
        elif user.get('certifications') == ".NET and Azure":
            batch = ".net batch"
        elif user.get('certifications') == "Python and SQL":
            batch = "data engineer"
        
        if batch and candidate_db.count_documents({'batch': batch}) < 30:
            candidate_db.update_one({'_id': ObjectId(session['user_id'])}, {'$set': {'batch': batch}})
        else:
            flash('Batch allocation limit reached or no certification matched.', 'danger')
        
        return render_template('batch_allocation.html', user=user, batch=batch)
    return redirect(url_for('login'))

@app.route('/course_recommendations')
def course_recommendations():
    if 'user_id' in session and session['user_type'] == 'candidate':
        user = candidate_db.find_one({'_id': ObjectId(session['user_id'])})
        if not user.get('courses_allocated'):
            batch = user.get('batch')
            try:
                # Generate course and job role recommendations using Google Gemini
                model = genai.GenerativeModel("gemini-1.5-flash")  # Specify the Gemini model
                
                # Course recommendations
                response_courses = model.generate_content(
                    f"Recommend online courses including YouTube courses for {batch} without links. Provide a list of 6 famous courses from the internet in bullet points in HTML format."
                )
                courses = response_courses.text.strip()

                # Job role recommendations
                response_jobs = model.generate_content(
                    f"What job roles are suitable for someone skilled in {batch}? Provide a list of 6 job roles and descriptions in HTML table format."
                )
                jobs = response_jobs.text.strip()

                # Update user document with recommendations
                candidate_db.update_one({'_id': ObjectId(session['user_id'])}, {'$set': {'courses_allocated': courses, 'job_roles': jobs}})
            except Exception as e:
                flash(f"Error generating recommendations: {e}", 'danger')
        
        return render_template('course_recommendations.html', courses=user.get('courses_allocated'), jobs=user.get('job_roles'))
    return redirect(url_for('login'))

@app.route('/tests_and_scores')
def tests_and_scores():
    if 'user_id' in session and session['user_type'] == 'candidate':
        user = candidate_db.find_one({'_id': ObjectId(session['user_id'])})
        batch = user.get('batch')
        test_questions = []
        if batch:
            try:
                # Generate test questions using Google Gemini
                model = genai.GenerativeModel("gemini-1.5-flash")  # Specify the Gemini model
                
                response_tests = model.generate_content(
                    f"Generate 15 test questions for the {batch} batch."
                )
                test_questions = response_tests.text.strip().split('\n')  # Assuming questions are separated by new lines

                # You might want to save or process the scores here
                # e.g., candidate_db.update_one({'_id': ObjectId(session['user_id'])}, {'$set': {'scores': new_scores}})
            except Exception as e:
                flash(f"Error generating test questions: {e}", 'danger')
        
        return render_template('tests_and_scores.html', test_questions=test_questions, scores=user.get('scores', []))
    return redirect(url_for('login'))

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
