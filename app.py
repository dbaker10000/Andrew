import os, secrets
from datetime import datetime
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import BooleanField, PasswordField, RadioField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Optional

db=SQLAlchemy(); migrate=Migrate(); csrf=CSRFProtect(); login_manager=LoginManager(); login_manager.login_view='login'
class User(UserMixin,db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); username=db.mapped_column(db.String(64),unique=True,nullable=False); password_hash=db.mapped_column(db.String(256),nullable=False); is_admin=db.mapped_column(db.Boolean,default=False); must_change=db.mapped_column(db.Boolean,default=True); reset_requested=db.mapped_column(db.Boolean,default=False); temporary_password=db.mapped_column(db.String(64)); decks=db.relationship('Deck',back_populates='owner',cascade='all, delete-orphan')
 def set_password(s,p):s.password_hash=generate_password_hash(p)
 def check_password(s,p):return check_password_hash(s.password_hash,p)
class Deck(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); title=db.mapped_column(db.String(160),nullable=False); description=db.mapped_column(db.Text); owner_id=db.mapped_column(db.ForeignKey('user.id'),nullable=False); created_at=db.mapped_column(db.DateTime,default=datetime.utcnow); owner=db.relationship('User',back_populates='decks'); cards=db.relationship('Card',back_populates='deck',cascade='all, delete-orphan',order_by='Card.position'); sessions=db.relationship('StudySession',cascade='all, delete-orphan'); tests=db.relationship('TestSession',cascade='all, delete-orphan')
class Card(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); deck_id=db.mapped_column(db.ForeignKey('deck.id'),nullable=False); prompt=db.mapped_column(db.Text,nullable=False); kind=db.mapped_column(db.String(20),default='narrative'); answer=db.mapped_column(db.Text); position=db.mapped_column(db.Integer,default=0); deck=db.relationship('Deck',back_populates='cards'); choices=db.relationship('Choice',cascade='all, delete-orphan',order_by='Choice.position')
class Choice(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); card_id=db.mapped_column(db.ForeignKey('card.id'),nullable=False); text=db.mapped_column(db.String(1000),nullable=False); correct=db.mapped_column(db.Boolean,default=False); position=db.mapped_column(db.Integer,default=0)
class StudySession(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); deck_id=db.mapped_column(db.ForeignKey('deck.id'),nullable=False); user_id=db.mapped_column(db.ForeignKey('user.id'),nullable=False); card_ids=db.mapped_column(db.JSON,nullable=False); index=db.mapped_column(db.Integer,default=0); completed_at=db.mapped_column(db.DateTime); attempts=db.relationship('Attempt',cascade='all, delete-orphan')
class Attempt(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); session_id=db.mapped_column(db.ForeignKey('study_session.id'),nullable=False); card_id=db.mapped_column(db.ForeignKey('card.id'),nullable=False); response=db.mapped_column(db.Text); score=db.mapped_column(db.Float)
class TestSession(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); deck_id=db.mapped_column(db.ForeignKey('deck.id'),nullable=False); user_id=db.mapped_column(db.ForeignKey('user.id'),nullable=False); card_ids=db.mapped_column(db.JSON,nullable=False); index=db.mapped_column(db.Integer,default=0); submitted_at=db.mapped_column(db.DateTime); graded_at=db.mapped_column(db.DateTime); answers=db.relationship('TestAnswer',cascade='all, delete-orphan')
class TestAnswer(db.Model):
 id=db.mapped_column(db.Integer,primary_key=True); test_id=db.mapped_column(db.ForeignKey('test_session.id'),nullable=False); card_id=db.mapped_column(db.ForeignKey('card.id'),nullable=False); response=db.mapped_column(db.Text); score=db.mapped_column(db.Float)
class LoginForm(FlaskForm): username=StringField('Username',validators=[DataRequired()]); password=PasswordField('Password',validators=[DataRequired()]); submit=SubmitField('Log in')
class DeckForm(FlaskForm): title=StringField('Deck title',validators=[DataRequired()]); description=TextAreaField('Description',validators=[Optional()]); submit=SubmitField('Save deck')
class CardForm(FlaskForm):
 prompt=TextAreaField('Question',validators=[DataRequired()]); kind=SelectField('Question type',choices=[('narrative','Written response'),('multiple_choice','Multiple choice')]); answer=TextAreaField('Correct answer / explanation'); a=StringField('Option A'); b=StringField('Option B'); c=StringField('Option C'); d=StringField('Option D'); correct=RadioField('Correct option',choices=[('0','A'),('1','B'),('2','C'),('3','D')],default='0'); submit=SubmitField('Save and close')
class PasswordForm(FlaskForm): password=PasswordField('New password',validators=[DataRequired()]); confirm=PasswordField('Confirm password',validators=[DataRequired(),EqualTo('password')]); submit=SubmitField('Update password')
class VerifyForm(FlaskForm): username=StringField('Username',validators=[DataRequired()]); password=PasswordField('Current password',validators=[DataRequired()]); submit=SubmitField('Continue')
class UserForm(FlaskForm): username=StringField('Username',validators=[DataRequired()]); temporary_password=StringField('Temporary password',validators=[DataRequired()]); is_admin=BooleanField('Administrator'); submit=SubmitField('Save user')
class ShareForm(FlaskForm): recipient=SelectField('Send a copy to',choices=[]); confirm=BooleanField('Make a copy for the selected recipient(s)'); submit=SubmitField('Send deck copy')
class ResetForm(FlaskForm): username=StringField('Username',validators=[DataRequired()]); submit=SubmitField('Request reset')
def create_app():
 a=Flask(__name__); a.config.update(SECRET_KEY=os.getenv('SECRET_KEY','dev'),SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL','sqlite:///flashcards.db'),SQLALCHEMY_TRACK_MODIFICATIONS=False,SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV')=='production'); db.init_app(a);migrate.init_app(a,db);csrf.init_app(a);login_manager.init_app(a)
 @login_manager.user_loader
 def load(i):return db.session.get(User,int(i))
 def deck(i):
  x=db.session.get(Deck,i)
  if not x or x.owner_id!=current_user.id:abort(404)
  return x
 def temp():return secrets.token_urlsafe(8)
 @a.route('/')
 @login_required
 def home():
  if current_user.must_change:return redirect(url_for('new_password'))
  decks=db.session.scalars(select(Deck).where(Deck.owner_id==current_user.id)).all(); stats={}
  for d in decks:
   done=[s for s in d.sessions if s.user_id==current_user.id and s.completed_at]; scores=[round(sum(x.score or 0 for x in s.attempts)/len(s.card_ids)*100) for s in done if s.card_ids]; tested=[s for s in d.tests if s.user_id==current_user.id and s.graded_at]; test_scores=[round(sum(x.score or 0 for x in s.answers)/len(s.card_ids)*100) for s in tested if s.card_ids]; stats[d.id]={'reviews':(len(scores),round(sum(scores)/len(scores)) if scores else None,scores[-1] if scores else None,max(scores) if scores else None),'tests':(len(test_scores),round(sum(test_scores)/len(test_scores)) if test_scores else None,test_scores[-1] if test_scores else None,max(test_scores) if test_scores else None)}
  return render_template('dashboard.html',decks=decks,stats=stats)
 @a.route('/login',methods=['GET','POST'])
 def login():
  if current_user.is_authenticated:return redirect(url_for('home'))
  f=LoginForm()
  if f.validate_on_submit():
   u=db.session.scalar(select(User).where(User.username==f.username.data.strip()))
   if u and u.check_password(f.password.data):
    if u.username==os.getenv('ADMIN_USERNAME') and f.password.data==os.getenv('ADMIN_PASSWORD'):
     u.must_change=True; db.session.commit()
    login_user(u);return redirect(url_for('new_password') if u.must_change else url_for('home'))
   flash('Invalid username or password.','danger')
  return render_template('login.html',form=f)
 @a.post('/logout')
 @login_required
 def logout():logout_user();return redirect(url_for('login'))
 @a.route('/reset-request',methods=['GET','POST'])
 def reset_request():
  f=ResetForm()
  if f.validate_on_submit():
   u=db.session.scalar(select(User).where(User.username==f.username.data.strip()))
   if u:u.temporary_password=temp();u.set_password(u.temporary_password);u.must_change=True;u.reset_requested=True;db.session.commit()
   flash('Your administrator has been notified. Ask them for your temporary password.','success');return redirect(url_for('login'))
  return render_template('reset_request.html',form=f)
 @a.route('/password/change',methods=['GET','POST'])
 @login_required
 def change_password():
  f=VerifyForm()
  if f.validate_on_submit() and f.username.data==current_user.username and current_user.check_password(f.password.data):session['verified']=True;return redirect(url_for('new_password'))
  return render_template('verify_password.html',form=f)
 @a.route('/password/new',methods=['GET','POST'])
 @login_required
 def new_password():
  if not current_user.must_change and not session.get('verified'):return redirect(url_for('change_password'))
  f=PasswordForm()
  if f.validate_on_submit():
   user=db.session.get(User,current_user.id);user.set_password(f.password.data);user.must_change=False;user.reset_requested=False;user.temporary_password=None;session.pop('verified',None);db.session.commit();login_user(user,fresh=True);flash('Password updated. Your deck library is ready.','success');return redirect(url_for('home'),code=303)
  return render_template('new_password.html',form=f)
 @a.route('/decks/new',methods=['GET','POST'])
 @login_required
 def new_deck():
  f=DeckForm()
  if f.validate_on_submit():x=Deck(title=f.title.data,description=f.description.data,owner_id=current_user.id);db.session.add(x);db.session.commit();return redirect(url_for('deck_view',id=x.id))
  return render_template('deck_form.html',form=f,deck=None)
 @a.route('/decks/<int:id>')
 @login_required
 def deck_view(id):return render_template('deck.html',deck=deck(id))
 @a.route('/decks/<int:id>/edit',methods=['GET','POST'])
 @login_required
 def edit_deck(id):
  x=deck(id);f=DeckForm(obj=x);share=ShareForm()
  if current_user.is_admin:share.recipient.choices=[('all','All users')]+[(str(u.id),u.username) for u in db.session.scalars(select(User).where(User.id!=current_user.id).order_by(User.username)).all()]
  if f.validate_on_submit():x.title=f.title.data;x.description=f.description.data;db.session.commit();return redirect(url_for('deck_view',id=id))
  return render_template('deck_form.html',form=f,deck=x,share_form=share)
 @a.post('/decks/<int:id>/share')
 @login_required
 def share_deck(id):
  admin();source=deck(id);f=ShareForm();users=db.session.scalars(select(User).where(User.id!=current_user.id).order_by(User.username)).all();f.recipient.choices=[('all','All users')]+[(str(u.id),u.username) for u in users]
  if not f.validate_on_submit() or not f.confirm.data:flash('Confirm that you want to create the deck copy.','danger');return redirect(url_for('edit_deck',id=id))
  recipients=users if f.recipient.data=='all' else [db.session.get(User,int(f.recipient.data))]
  for recipient in recipients:
   if not recipient:continue
   copy=Deck(title=source.title,description=source.description,owner_id=recipient.id);db.session.add(copy);db.session.flush()
   for card in source.cards:
    card_copy=Card(deck_id=copy.id,prompt=card.prompt,kind=card.kind,answer=card.answer,position=card.position);db.session.add(card_copy);db.session.flush()
    for choice in card.choices:db.session.add(Choice(card_id=card_copy.id,text=choice.text,correct=choice.correct,position=choice.position))
  db.session.commit();flash(f'Deck copied to {len(recipients)} user(s).','success');return redirect(url_for('edit_deck',id=id))
 @a.post('/decks/<int:id>/delete')
 @login_required
 def delete_deck(id):db.session.delete(deck(id));db.session.commit();return redirect(url_for('home'))
 def save_card(f,d,c=None):
  c=c or Card(deck_id=d.id,position=len(d.cards));c.prompt=f.prompt.data;c.kind=f.kind.data;c.answer=f.answer.data;c.choices.clear()
  if c.kind=='multiple_choice':
   vals=[f.a.data,f.b.data,f.c.data,f.d.data]
   if not all(vals):flash('Enter all four choices.','danger');return None
   for i,v in enumerate(vals):c.choices.append(Choice(text=v,correct=str(i)==f.correct.data,position=i))
  db.session.add(c);db.session.commit();return c
 @a.route('/decks/<int:id>/cards/new',methods=['GET','POST'])
 @login_required
 def new_card(id):
  d=deck(id);f=CardForm()
  if f.validate_on_submit() and save_card(f,d):return redirect(url_for('new_card',id=id) if request.form.get('action')=='new' else url_for('deck_view',id=id))
  return render_template('card_form.html',form=f,deck=d,card=None)
 @a.route('/cards/<int:id>/edit',methods=['GET','POST'])
 @login_required
 def edit_card(id):
  c=db.session.get(Card,id);d=deck(c.deck_id) if c else abort(404);f=CardForm(obj=c)
  if request.method=='GET' and c.kind=='multiple_choice':
   for i,x in enumerate(c.choices):getattr(f,'abcd'[i]).data=x.text;f.correct.data=str(i) if x.correct else f.correct.data
  if f.validate_on_submit() and save_card(f,d,c):return redirect(url_for('deck_view',id=d.id))
  return render_template('card_form.html',form=f,deck=d,card=c)
 @a.post('/cards/<int:id>/delete')
 @login_required
 def delete_card(id):c=db.session.get(Card,id);d=deck(c.deck_id) if c else abort(404);db.session.delete(c);db.session.commit();return redirect(url_for('deck_view',id=d.id))
 @a.post('/decks/<int:id>/study')
 @login_required
 def start(id):
  d=deck(id);ids=[x.id for x in d.cards];secrets.SystemRandom().shuffle(ids)
  if not ids:flash('Add a card before studying.','warning');return redirect(url_for('deck_view',id=id))
  s=StudySession(deck_id=id,user_id=current_user.id,card_ids=ids);db.session.add(s);db.session.commit();return redirect(url_for('study',id=s.id))
 @a.route('/study/<int:id>')
 @login_required
 def study(id):
  s=db.session.get(StudySession,id)
  if not s or s.user_id!=current_user.id:abort(404)
  if s.completed_at:return render_template('complete.html',study=s,score=round(sum(x.score or 0 for x in s.attempts)/len(s.card_ids)*100))
  return render_template('study.html',study=s,card=db.session.get(Card,s.card_ids[s.index]),number=s.index+1)
 @a.post('/study/<int:id>/answer')
 @login_required
 def answer(id):
  s=db.session.get(StudySession,id);c=db.session.get(Card,s.card_ids[s.index]) if s and s.user_id==current_user.id else abort(404);r=request.form.get('response','')
  if c.kind=='narrative':x=Attempt(session_id=s.id,card_id=c.id,response=r);db.session.add(x);db.session.commit();return render_template('grade.html',study=s,card=c,attempt=x)
  ch=db.session.get(Choice,int(r)) if r.isdigit() else None;db.session.add(Attempt(session_id=s.id,card_id=c.id,response=r,score=1 if ch and ch.correct else 0));s.index+=1;s.completed_at=datetime.utcnow() if s.index==len(s.card_ids) else None;db.session.commit();return redirect(url_for('study',id=s.id))
 @a.post('/study/<int:id>/grade/<int:aid>')
 @login_required
 def grade(id,aid):s=db.session.get(StudySession,id);x=db.session.get(Attempt,aid);x.score=float(request.form['score']);s.index+=1;s.completed_at=datetime.utcnow() if s.index==len(s.card_ids) else None;db.session.commit();return redirect(url_for('study',id=id))
 @a.post('/decks/<int:id>/test')
 @login_required
 def start_test(id):
  d=deck(id);ids=[x.id for x in d.cards];secrets.SystemRandom().shuffle(ids)
  if not ids:flash('Add a card before starting a test.','warning');return redirect(url_for('deck_view',id=id))
  t=TestSession(deck_id=id,user_id=current_user.id,card_ids=ids);db.session.add(t);db.session.commit();return redirect(url_for('take_test',id=t.id))
 @a.route('/tests/<int:id>')
 @login_required
 def take_test(id):
  t=db.session.get(TestSession,id)
  if not t or t.user_id!=current_user.id:abort(404)
  if t.submitted_at:return render_template('test_submitted.html',test=t)
  return render_template('test.html',test=t,card=db.session.get(Card,t.card_ids[t.index]),number=t.index+1)
 @a.post('/tests/<int:id>/answer')
 @login_required
 def test_answer(id):
  t=db.session.get(TestSession,id)
  if not t or t.user_id!=current_user.id or t.submitted_at:abort(404)
  c=db.session.get(Card,t.card_ids[t.index]);db.session.add(TestAnswer(test_id=t.id,card_id=c.id,response=request.form.get('response','')));t.index+=1;t.submitted_at=datetime.utcnow() if t.index==len(t.card_ids) else None;db.session.commit();return redirect(url_for('take_test',id=t.id))
 def admin():
  if not current_user.is_admin:abort(403)
 @a.route('/admin/users')
 @login_required
 def users():admin();return render_template('users.html',users=db.session.scalars(select(User).order_by(User.username)).all())
 @a.route('/admin/tests')
 @login_required
 def admin_tests():
  admin();tests=db.session.scalars(select(TestSession).where(TestSession.submitted_at.is_not(None)).order_by(TestSession.submitted_at.desc())).all();rows=[(t,db.session.get(Deck,t.deck_id),db.session.get(User,t.user_id)) for t in tests];return render_template('admin_tests.html',rows=rows)
 @a.route('/admin/tests/<int:id>/grade',methods=['GET','POST'])
 @login_required
 def grade_test(id):
  admin();t=db.session.get(TestSession,id) or abort(404)
  if request.method=='POST':
   for answer in t.answers:answer.score=float(request.form.get(f'score_{answer.id}',0))
   t.graded_at=datetime.utcnow();db.session.commit();flash('Test graded.','success');return redirect(url_for('admin_tests'))
  cards={x.id:x for x in db.session.scalars(select(Card).where(Card.id.in_([a.card_id for a in t.answers]))).all()};user=db.session.get(User,t.user_id);deck=db.session.get(Deck,t.deck_id);return render_template('grade_test.html',test=t,cards=cards,user=user,deck=deck)
 @a.post('/admin/tests/<int:id>/delete')
 @login_required
 def delete_test(id):
  admin();t=db.session.get(TestSession,id) or abort(404)
  if not t.graded_at:abort(400)
  db.session.delete(t);db.session.commit();flash('Graded test deleted.','success');return redirect(url_for('admin_tests'))
 @a.route('/admin/users/new',methods=['GET','POST'])
 @login_required
 def new_user():
  admin();f=UserForm()
  if f.validate_on_submit():u=User(username=f.username.data,is_admin=f.is_admin.data,temporary_password=f.temporary_password.data);u.set_password(u.temporary_password);db.session.add(u);db.session.commit();return redirect(url_for('users'))
  return render_template('user_form.html',form=f)
 @a.post('/admin/users/<int:id>/reset')
 @login_required
 def reset_user(id):admin();u=db.session.get(User,id) or abort(404);u.temporary_password=temp();u.set_password(u.temporary_password);u.must_change=True;u.reset_requested=False;db.session.commit();return redirect(url_for('users'))
 @a.cli.command('bootstrap-admin')
 def bootstrap_admin():
  username,password=os.getenv('ADMIN_USERNAME'),os.getenv('ADMIN_PASSWORD')
  if not username or not password: raise RuntimeError('Set ADMIN_USERNAME and ADMIN_PASSWORD.')
  if db.session.scalar(select(User).where(User.username==username)): print('Administrator already exists.'); return
  u=User(username=username,is_admin=True,must_change=True,temporary_password=password);u.set_password(password);db.session.add(u);db.session.commit();print('Administrator created.')
 return a
