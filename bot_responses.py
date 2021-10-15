# Replies to comment with text=body
import prawcore


def reply(comment_or_submission, body):
    response = body + "\n\n^(This action was performed by a bot, please contact the mods for any questions.)"
    response += "[See disclaimer](https://www.reddit.com/user/Vault-TecTradingCo/comments/lkllre" \
                "/disclaimer_for_rfallout76marketplace/)) "
    try:
        new_comment = comment_or_submission.reply(response)
        new_comment.mod.distinguish(how="yes")
        new_comment.mod.lock()
    except prawcore.exceptions.Forbidden:
        pass


def transfer_successful(comment, m76_karma, total_karma):
    comment_body = f"Hi {comment.author.name}! The bot was successfully able to transfer {m76_karma} karma from " \
                   f"Market76 to here. Your total karma is now {total_karma}.You can transfer karma to here only once. " \
                   f"Note that here karma is given on successful trade and only be given once per trade. Also, you are " \
                   f"limited to giving 10 karma per day.\n\nThank you for your cooperation!"
    reply(comment, comment_body)


def no_karma_on_market76(comment):
    comment_body = "Hi " + comment.author.name + "! It seems that you do not have any karma on Market 76. Sorry."
    reply(comment, comment_body)


def already_transferred(comment, result):
    comment_body = "Hi " + comment.author.name + "! It seems that you already have transferred {} ".format(result[2])
    comment_body += "karma from Market76 on {}. You can see your comment [here]({})".format(result[0], result[3])
    reply(comment, comment_body)


def no_submission_found(comment):
    comment_body = "Hi " + comment.author.name + "! The bot looked at your past ~1000 submissions and could not find. "
    comment_body += "any that were posted to market76. Please contact mods if you think this is a mistake."
    reply(comment, comment_body)


def something_went_wrong(comment, subreddit_name):
    comment_body = "Hi " + comment.author.name + "! something went wrong while getting "
    comment_body += "karma from {}. Please contact mods asap.".format(subreddit_name)
    reply(comment, comment_body)

def transfer_information(comment, row, username):
    if row:
        comment_body = f"The reddit user {row[1]} transferred {row[2]} karma from Market76 on {row[0]}. Following is " \
                       f"the direct link to their comment: [Comment Link]({row[3]})"
    else:
        comment_body = f"The reddit user {username} has not yet transferred their karma from Market76. If you are " \
                       f"that user, you may transfer karma by commenting \"!xferkarma\" (without quotes)."
    reply(comment, comment_body)
