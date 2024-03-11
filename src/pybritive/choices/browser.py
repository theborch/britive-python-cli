import os
import click

# eval example: eval $(pybritive checkout test -m env)

browser_choices = click.Choice(
    [
        'mozilla',
        'firefox',
        'windows-default',
        'macosx',
        'safari',
        'chrome',
        'chromium',
        os.getenv('PYBRITIVE_BROWSER')
    ],
    case_sensitive=False
)