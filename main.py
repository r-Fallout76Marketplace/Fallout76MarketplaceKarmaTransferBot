import datetime
import json
import re
import sqlite3
import time
import traceback

import prawcore
import requests

import CONFIG
import bot_responses

# global variable
karma_transfer_db = sqlite3.connect('karma_transfer_history.db')
command = r'^(xferkarma!|!xferkarma)$'

ABOVE_HUNDRED_FLAIR = "0467e0de-4a4d-11eb-9453-0e4e6fcf2865"
FIFTY_TO_HUNDRED_FLAIR = "2624bc6a-4a4d-11eb-8b7c-0e6968d78889"
ZERO_TO_FIFTY_FLAIR = "3c680234-4a4d-11eb-8124-0edd2b620987"


# Send message to discord channel
def send_message_to_discord(message_param):
    data = {"content": message_param, "username": CONFIG.bot_name}
    output = requests.post(CONFIG.discord_webhooks, data=json.dumps(data), headers={"Content-Type": "application/json"})
    output.raise_for_status()


def assign_flair(karma_value, author_name):
    user_flair = 'Karma: {}'.format(karma_value)
    if karma_value < 49:
        CONFIG.fallout76marketplace.flair.set(author_name, text=str(user_flair), flair_template_id=ZERO_TO_FIFTY_FLAIR)
    elif 50 <= karma_value < 99:
        CONFIG.fallout76marketplace.flair.set(author_name, text=str(user_flair),
                                              flair_template_id=FIFTY_TO_HUNDRED_FLAIR)
    else:
        CONFIG.fallout76marketplace.flair.set(author_name, text=str(user_flair),
                                              flair_template_id=ABOVE_HUNDRED_FLAIR)


def transfer_karma(comment, submission):
    author_name = comment.author.name
    cursor = karma_transfer_db.cursor()
    current_date_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %I:%M %p UTC')
    if submission.author_flair_text is None:
        bot_responses.no_karma_on_market76(comment)
        return

    cursor.execute("SELECT * from karma_transfer_history WHERE author_name='{}'".format(comment.author.name))
    result = cursor.fetchone()
    if result is not None:
        bot_responses.already_transferred(comment, result)
        return
    # Get karma from market 76
    user_flair = submission.author_flair_text.split()
    our_karma = 0
    try:
        m76_karma = int(user_flair[0][1:])
    except ValueError:
        bot_responses.something_went_wrong(comment, "r/Market76")
        return

    # Get karma from f076mktpl
    user_flair = comment.author_flair_text
    if user_flair is not None:
        if "Karma:" in user_flair:
            try:
                user_flair = comment.author_flair_text.split()
                our_karma = int(user_flair[-1])
            except ValueError or AttributeError:
                bot_responses.something_went_wrong(comment, "r/Fallout76Marketplace")
                return

    total_karma = m76_karma + our_karma
    assign_flair(karma_value=total_karma, author_name=author_name)
    url = 'https://www.reddit.com{}'.format(comment.permalink)
    cursor.execute("""INSERT INTO karma_transfer_history VALUES ('{}', '{}', '{}', '{}')""".format(current_date_time,
                                                                                                   author_name,
                                                                                                   m76_karma,
                                                                                                   url))
    karma_transfer_db.commit()
    cursor.close()
    bot_responses.transfer_successful(comment, m76_karma)
    return


def check_comments(comment):
    comment_body = comment.body.lower().strip()
    if re.search(command, comment_body, re.IGNORECASE):
        author = comment.author
        submissions = author.submissions.new(limit=None)
        for submission in submissions:
            if submission.subreddit == CONFIG.market76:
                transfer_karma(comment, submission)
                return 1
        return -1
    return 0


def main():
    failed_attempt = 1
    comment_stream = CONFIG.fallout76marketplace.stream.comments(pause_after=-1, skip_existing=True)
    while True:
        try:
            for comment in comment_stream:
                if comment is None:
                    break
                if check_comments(comment) == -1:
                    bot_responses.no_submission_found(comment)
                failed_attempt = 1
        except KeyboardInterrupt:
            print("Bot has stopped!", time.strftime('%I:%M %p %Z'))
            quit()
        except Exception as exception:
            tb = traceback.format_exc()
            print(tb)
            try:
                send_message_to_discord(tb)
            except Exception:
                print("Error sending message to discord")
            # In case of server error pause for two minutes
            if isinstance(exception, prawcore.exceptions.ServerError):
                print("Waiting 2 minutes")
                # Try again after a pause
                time.sleep(120 * failed_attempt)
                failed_attempt = failed_attempt + 1
            comment_stream = CONFIG.fallout76marketplace.stream.comments(pause_after=-1, skip_existing=True)


# Entry point
if __name__ == '__main__':
    # create table if doesn't exist
    cursor = karma_transfer_db.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS karma_transfer_history (
                                                    date text,
                                                    author_name text,
                                                    karma INTEGER,
                                                    comment_url text
                                                    )""")
    karma_transfer_db.commit()
    cursor.close()
    print("Bot is now live!", time.strftime('%I:%M %p %Z'))
    main()
