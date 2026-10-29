"""
python -m helpdesk "What time do you open on Saturday?"   single question
python -m helpdesk                                         chat, empty line quits
"""

import logging
import os
import sys

from dotenv import load_dotenv

from helpdesk.agent import Agent, OpenAICompatibleModel


def main() -> None:
    load_dotenv()
    # Windows consoles default to cp1250/cp1252 and models like narrow no-break spaces
    sys.stdout.reconfigure(errors="replace")
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"), format="%(levelname)s %(message)s")
    agent = Agent(OpenAICompatibleModel())

    if len(sys.argv) > 1:
        print(agent.ask(" ".join(sys.argv[1:])).text)
        return

    print("CityWheels help desk. Ask a question, empty line to quit.")
    try:
        while question := input("> ").strip():
            print(agent.ask(question).text)
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
