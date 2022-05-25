import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query databases
    portfolio = db.execute("SELECT * FROM portfolio WHERE person_id is ?", session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id is ?", session["user_id"])

    # If portfolio has entries display those entries as a table
    if len(portfolio):
        cash = user[0]["cash"]

        # Create index for each company in portfolio
        net = 0
        index = []

        for company in portfolio:
            stock = lookup(company["symbol"])
            net += stock["price"] * company["shares"]
            index.append({"symbol": stock["symbol"], "name": stock["name"], "shares": company["shares"],
                         "price": stock["price"], "total": stock["price"] * company["shares"]})

        # Totals cash + holdings value
        net += cash
        return render_template("index.html", index=index, cash=cash, net=net)

    # If portfolio is empty, return apology message.
    else:
        return apology("Opps, you don't have any stocks!")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        if not request.form.get("shares").isnumeric():
            return apology("Enter a numeric value", 400)

        # If symbol and shared entered are valid, create usable variables
        if lookup(request.form.get("symbol")) and float(request.form.get("shares")) > 0:
            results = lookup(request.form.get("symbol"))
            total = float(results["price"]) * float(request.form.get("shares"))
            cash = db.execute("SELECT cash FROM users WHERE id is ?", session["user_id"])
            name = db.execute("SELECT username FROM users WHERE id is ?", session["user_id"])

            # Verifies users available cash
            if total <= cash[0]["cash"]:

                # Gets new account balance
                balance = cash[0]["cash"] - total

                # Adds company to portfolio database or updates existing portfolio entry with new purchase
                purchased = db.execute("SELECT symbol FROM portfolio WHERE symbol is ? AND person_id is ?",
                                       results["symbol"], session["user_id"])
                if len(purchased) > 0:
                    db.execute("UPDATE portfolio SET shares=? + shares WHERE symbol is ? AND person_id is ?",
                               request.form.get("shares"), results["symbol"], session["user_id"])
                else:
                    db.execute("INSERT INTO portfolio (symbol, name, shares, person_id) VALUES(?, ?, ?, ?)",
                               results["symbol"], results["name"], request.form.get("shares"), session["user_id"])

                # Updates purchase history database
                db.execute("INSERT INTO history (person_id, username, shares, symbol, price_per_share, company_name, date) VALUES(?, ?, ?, ? ,?, ?, ?)", session["user_id"],
                           name[0]["username"], request.form.get("shares"), results["symbol"], results["price"], results["name"], datetime.datetime.now(datetime.timezone.utc))

                # Updates users database with new balance
                db.execute("UPDATE users SET cash=? WHERE id is ?", balance, session["user_id"])
                return render_template("bought.html", name=results["name"], symbol=results["symbol"], price=results["price"], total=total, shares=request.form.get("shares"), balance=balance)

            # If user doesn't have enough money return error.
            else:
                return apology("you do not have sufficient funds", 400)

        # If symbol is not valid return an error
        else:
            return apology("must enter a valid company symbol and positive shares value", 400)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query history database for users data
    history = db.execute("SELECT * FROM history WHERE person_id is ? ORDER BY date desc", session["user_id"])

    # If history has entries display those entries as a table
    if len(history):
        return render_template("history.html", history=history)

    # If history is empty, return apology message.
    else:
        return apology("Opps, it looks like you haven't made your first trade yet")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 200)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")

    else:
        if lookup(request.form.get("symbol")):
            results = lookup(request.form.get("symbol"))
            return render_template("quoted.html", name=results["name"], symbol=results["symbol"], price=results["price"])

        else:
            return apology("invalid company symbol", 400)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")

    else:
        # Query database for username
        username = request.form.get("username")

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password and confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password must match", 400)

        # Ensures username doesn't exist already
        elif len(db.execute("SELECT * FROM users WHERE username = ?", username)) > 0:
            return apology("username already exists", 400)

        # Adds new user to database
        else:
            hashed = generate_password_hash(request.form.get("password"))
            user = db.execute("INSERT INTO users (username, hash, join_date) VALUES(?, ?, ?)",
                              username, hashed, datetime.datetime.today())
            session["user_id"] = user
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        portfolio = db.execute("SELECT * FROM portfolio WHERE person_id is ?", session["user_id"])
        return render_template("sell.html", portfolio=portfolio)

    else:
        # If user inputs valid shares number, generate usable variables
        if float(request.form.get("shares")) > 0:
            results = lookup(request.form.get("symbol"))

            total = float(results["price"]) * float(request.form.get("shares"))
            cash = db.execute("SELECT cash FROM users WHERE id is ?", session["user_id"])
            name = db.execute("SELECT username FROM users WHERE id is ?", session["user_id"])
            shares = db.execute("SELECT shares FROM portfolio WHERE symbol is ? AND person_id=?",
                                request.form.get("symbol"), session["user_id"])

            # Verifies users available shares
            if float(shares[0]["shares"]) >= float(request.form.get("shares")):

                # Gets new account balance
                balance = cash[0]["cash"] + total

                # If there are no remaining shares, delete entry from portfolio database
                db.execute("UPDATE portfolio SET shares=(shares-?) WHERE symbol is ? AND person_id is ?",
                           request.form.get("shares"), results["symbol"], session["user_id"])
                temp = db.execute("SELECT shares FROM portfolio WHERE symbol is ? AND person_id=?",
                                  request.form.get("symbol"), session["user_id"])
                if int(temp[0]["shares"]) <= 0.0:
                    db.execute("DELETE FROM portfolio WHERE symbol is ?", results["symbol"])

                # Updates purchase history database
                db.execute("INSERT INTO history (person_id, username, shares, symbol, price_per_share, type, company_name, date) VALUES(?, ?, ?, ? ,?, 'Sold', ?, ?)", session["user_id"], name[0]["username"],
                           request.form.get("shares"), results["symbol"], results["price"], results["name"], datetime.datetime.now(datetime.timezone.utc))

                # updates users database with new balance
                db.execute("UPDATE users SET cash=? WHERE id is ?", balance, session["user_id"])
                return render_template("sold.html", name=results["name"], symbol=results["symbol"], price=results["price"], total=total, shares=request.form.get("shares"), balance=balance)

            # If user doesn't have enough shares return error.
            else:
                return apology("you do not have sufficient shares", 400)

        # If symbol is not valid return an error
        else:
            return apology("must enter a valid company symbol and positive shares value")


@app.route("/profile")
@login_required
def profile():

    user = db.execute("SELECT * FROM users WHERE id is ?", session["user_id"])
    return render_template("profile.html", user=user)


@app.route("/reset", methods=["GET", "POST"])
@login_required
def reset():

    user = db.execute("SELECT * FROM users WHERE id is ?", session["user_id"])

    if request.method == "GET":
        return render_template("reset.html")
    else:

        # Ensure old password was submitted
        if not request.form.get("password"):
            return apology("must provide old password", 403)

        # Ensure new password was submitted
        elif not request.form.get("new_password"):
            return apology("must provide a new password", 403)

        # Ensure password and confirmation match
        elif request.form.get("new_password") != request.form.get("confirmation"):
            return apology("password must match", 403)

        # Updates user database with new password
        else:
            hashed_new = generate_password_hash(request.form.get("new_password"))

            # Confirm old password was entered correctly
            if check_password_hash(user[0]["hash"], request.form.get("password")):
                db.execute("UPDATE users SET hash=? WHERE id is ?", hashed_new, session["user_id"])
                return redirect("/profile")
            else:
                return apology("Entered invalid old password")


@app.route("/addCash", methods=["GET", "POST"])
@login_required
def addCash():

    if request.method == "GET":

        return render_template("addCash.html")

    else:
        # Adds cash to balance
        cash = request.form.get("cash")
        db.execute("UPDATE users SET cash=(? + cash) WHERE id is ?", cash, session["user_id"])
        return redirect("/profile")