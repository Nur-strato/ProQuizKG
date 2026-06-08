import sys
from app import app, db, User


def set_status(login_name, status):
    with app.app_context():
        user = User.query.filter_by(login=login_name).first()
        if user:
            user.status = status
            db.session.commit()
            print(f"\n✅ УСПЕХ: Пользователю '{login_name}' присвоен статус '{status}'.\n")
        else:
            print(f"\n❌ ОШИБКА: Пользователь '{login_name}' не найден.\n")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("\nИспользование:")
        print("  python manage.py add <логин>    - дать админку")
        print("  python manage.py remove <логин> - забрать админку\n")
    else:
        action = sys.argv[1]
        username = sys.argv[2]

        if action == 'add':
            set_status(username, 'admin')
        elif action == 'remove':
            set_status(username, 'user')
        else:
            print("Неизвестная команда. Используй 'add' или 'remove'.")