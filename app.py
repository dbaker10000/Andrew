import os
from datetime import datetime

import click
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


class User(UserMixin, db.Model):
    id = db.mapped_column(db.Integer, primary_key=True)
    username = db.mapped_column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.mapped_column(db.String(256), nullable=False)
    is_admin = db.mapped_column(db.Boolean, default=False, nullable=False)
    created_at = db.mapped_column(db.DateTime, default=datetime.utcnow, nullable=False)
    tasks = db.relationship("Task", back_populates="owner", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    id = db.mapped_column(db.Integer, primary_key=True)
    title = db.mapped_column(db.String(160), nullable=False)
    description = db.mapped_column(db.Text, nullable=True)
    status = db.mapped_column(db.String(20), default="open", nullable=False, index=True)
    priority = db.mapped_column(db.String(20), default="medium", nullable=False)
    due_date = db.mapped_column(db.Date, nullable=True)
    created_at = db.mapped_column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.mapped_column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    owner_id = db.mapped_column(db.ForeignKey("user.id"), nullable=False, index=True)
    owner = db.relationship("User", back_populates="tasks")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class TaskForm(FlaskForm):
    title = StringField("Task title", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=5000)])
    status = SelectField("Status", choices=[("open", "Open"), ("in_progress", "In progress"), ("completed", "Completed")])
    priority = SelectField("Priority", choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")])
    due_date = StringField("Due date", validators=[Optional()], render_kw={"type": "date"})
    submit = SubmitField("Save task")


class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField("Password", validators=[Optional(), Length(min=10, max=128)])
    is_admin = BooleanField("Administrator")
    submit = SubmitField("Save user")


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///andrew.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    def owned_task(task_id):
        task = db.session.get(Task, task_id)
        if not task or (task.owner_id != current_user.id and not current_user.is_admin):
            abort(404)
        return task

    @app.context_processor
    def utility_processor():
        return {"now": datetime.utcnow}

    @app.route("/")
    @login_required
    def dashboard():
        status = request.args.get("status", "all")
        statement = select(Task).where(Task.owner_id == current_user.id).order_by(Task.created_at.desc())
        if status in {"open", "in_progress", "completed"}:
            statement = statement.where(Task.status == status)
        tasks = db.session.scalars(statement).all()
        counts = {key: db.session.scalar(select(db.func.count()).select_from(Task).where(Task.owner_id == current_user.id, Task.status == key)) for key in ("open", "in_progress", "completed")}
        return render_template("dashboard.html", tasks=tasks, counts=counts, active_status=status)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        form = LoginForm()
        if form.validate_on_submit():
            user = db.session.scalar(select(User).where(User.username == form.username.data.strip()))
            if user and user.check_password(form.password.data):
                login_user(user)
                return redirect(request.args.get("next") or url_for("dashboard"))
            flash("Invalid username or password.", "danger")
        return render_template("login.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/tasks/new", methods=["GET", "POST"])
    @login_required
    def create_task():
        form = TaskForm()
        if form.validate_on_submit():
            task = Task(title=form.title.data.strip(), description=form.description.data.strip() or None, status=form.status.data, priority=form.priority.data, due_date=datetime.strptime(form.due_date.data, "%Y-%m-%d").date() if form.due_date.data else None, owner=current_user)
            db.session.add(task); db.session.commit()
            flash("Task created.", "success")
            return redirect(url_for("dashboard"))
        return render_template("task_form.html", form=form, task=None)

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_task(task_id):
        task = owned_task(task_id)
        form = TaskForm(obj=task)
        if request.method == "GET" and task.due_date:
            form.due_date.data = task.due_date.isoformat()
        if form.validate_on_submit():
            task.title, task.description, task.status, task.priority = form.title.data.strip(), form.description.data.strip() or None, form.status.data, form.priority.data
            task.due_date = datetime.strptime(form.due_date.data, "%Y-%m-%d").date() if form.due_date.data else None
            db.session.commit(); flash("Task updated.", "success")
            return redirect(url_for("dashboard"))
        return render_template("task_form.html", form=form, task=task)

    @app.post("/tasks/<int:task_id>/delete")
    @login_required
    def delete_task(task_id):
        db.session.delete(owned_task(task_id)); db.session.commit()
        flash("Task deleted.", "success")
        return redirect(url_for("dashboard"))

    def require_admin():
        if not current_user.is_admin:
            abort(403)

    @app.route("/admin/users")
    @login_required
    def users():
        require_admin()
        return render_template("users.html", users=db.session.scalars(select(User).order_by(User.username)).all())

    @app.route("/admin/users/new", methods=["GET", "POST"])
    @login_required
    def create_user():
        require_admin(); form = UserForm()
        if form.validate_on_submit():
            if db.session.scalar(select(User).where(User.username == form.username.data.strip())):
                form.username.errors.append("That username is already in use.")
            elif not form.password.data:
                form.password.errors.append("A password is required for a new user.")
            else:
                user = User(username=form.username.data.strip(), is_admin=form.is_admin.data); user.set_password(form.password.data)
                db.session.add(user); db.session.commit(); flash("User created.", "success")
                return redirect(url_for("users"))
        return render_template("user_form.html", form=form, user=None)

    @app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_user(user_id):
        require_admin(); user = db.session.get(User, user_id) or abort(404); form = UserForm(obj=user)
        if form.validate_on_submit():
            candidate = db.session.scalar(select(User).where(User.username == form.username.data.strip(), User.id != user.id))
            if candidate: form.username.errors.append("That username is already in use.")
            elif user.id == current_user.id and not form.is_admin.data: form.is_admin.errors.append("You cannot remove your own administrator access.")
            else:
                user.username, user.is_admin = form.username.data.strip(), form.is_admin.data
                if form.password.data: user.set_password(form.password.data)
                db.session.commit(); flash("User updated.", "success")
                return redirect(url_for("users"))
        return render_template("user_form.html", form=form, user=user)

    @app.post("/admin/users/<int:user_id>/delete")
    @login_required
    def delete_user(user_id):
        require_admin(); user = db.session.get(User, user_id) or abort(404)
        if user.id == current_user.id or user.is_admin:
            flash("You cannot delete your own account or an administrator account.", "danger")
        else:
            db.session.delete(user); db.session.commit(); flash("User deleted.", "success")
        return redirect(url_for("users"))

    @app.cli.command("bootstrap-admin")
    def bootstrap_admin():
        """Create initial administrator from ADMIN_USERNAME and ADMIN_PASSWORD."""
        username, password = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
        if not username or not password: raise click.ClickException("Set ADMIN_USERNAME and ADMIN_PASSWORD.")
        if db.session.scalar(select(User).where(User.username == username)): raise click.ClickException("Administrator already exists.")
        user = User(username=username, is_admin=True); user.set_password(password)
        db.session.add(user); db.session.commit(); click.echo("Administrator created.")

    return app
