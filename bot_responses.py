# Replies to comment with text=body
import prawcore


def reply(comment_or_submission, body):
    response = body + "\n\n ^(This action was performed by a bot, please contact the mods for any questions.)"
    try:
        new_comment = comment_or_submission.reply(response)
        new_comment.mod.distinguish(how="yes")
        new_comment.mod.lock()
    except prawcore.exceptions.Forbidden:
        pass


def transfer_successful(comment, karma):
    comment_body = "Hi " + comment.author.name + "! The bot was successfully able to transfer {} karma ".format(karma)
    comment_body += "from Market76 to here. Please note that you can transfer karma only once.\n\nNote that here karma "
    comment_body += "is given on successful trade and only be given once per trade. If your karma is below 100, you "
    comment_body += "can have a limit on how much karma you can give per day. You can find more info by checking the "
    comment_body += "[pinned post](https://www.reddit.com/r/Fallout76Marketplace/comments/lf5wjp/karma_bot_new_update/)"
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


def something_went_wrong(comment):
    comment_body = "Hi " + comment.author.name + "! something went wrong. Please contact mods asap."
    reply(comment, comment_body)
