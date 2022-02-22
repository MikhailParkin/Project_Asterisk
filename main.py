import os
import sys
import mysql.connector
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QMessageBox, QApplication
from PyQt5 import QtCore, QtGui
import main_gui
import re
import paramiko
import datetime
import threading
import xlsxwriter


local_path = 'C:/Obzvon'
local_path_file = 'C:/Obzvon/tmp/'
remote_path = '/root/asterisk/tmp'
remote_path_end = '/var/spool/asterisk/outgoing'


time_now = 0
year = None
month = None
day = None
hour = None


class ParentWindow(QMainWindow, main_gui.Ui_MainWindow):
    day_start = None
    day_end = None
    month_start = None
    month_end = None
    year_start = None
    year_end = None
    calls = None

    server_cent = '127.0.0.1'
    username_cent = 'root'
    password_cent = 'password'
    username_sql = 'asterisk'
    password_sql = 'asterisk'

    ring_in_day = 12000  # Количество звонков в день
    bd_fiz = 'asterisk.obzvon_number'
    bd_ul = 'asterisk.obzvon_ul'

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.dlg = QFileDialog()
        self.dlg_m = QMessageBox()
        self.timer = QtCore.QTimer()
        self.show()
        self.dateEdit_2.setDate(QtCore.QDate.currentDate())
        self.dateEdit_3.setDate(QtCore.QDate.currentDate())
        self.dateEdit_2.dateChanged.connect(self.date_change)
        self.dateEdit_3.dateChanged.connect(self.date_change)
        self.date_change()
        self.date_now()
        self.toolButton.clicked.connect(self.show_open_dialog)
        self.pushButton.clicked.connect(self.start_all)
        self.pushButton_2.clicked.connect(self.load_report)
        self.pushButton_3.clicked.connect(lambda: self.save_xlsx(calls=self.calls))
        self.timer.timeout.connect(self.stat_call)
        # self.stat_call()
        # self.timer.start(10000)

    def show_open_dialog(self):
        if os.path.exists(local_path) is not True:
            try:
                os.mkdir(local_path)
                os.mkdir(local_path_file)
            except OSError:
                message = f'Создать директорию {local_path} не удалось'
                self.alert_message(message)

        f = self.dlg.getOpenFileName(self, 'Open file', local_path, 'Разделители запятые (*.csv)')[0]
        self.lineEdit.setText(f)

    def alert_message(self, message):
        self.dlg_m.show()
        self.dlg_m.setIcon(QMessageBox.Information)
        self.dlg_m.setWindowTitle("Info")
        self.dlg_m.setText('Внимание!')
        self.dlg_m.setInformativeText(message)

    def date_now(self):
        now = datetime.datetime.now()
        global year, month, day, hour
        year = now.year
        month = now.month
        day = now.day
        hour = now.hour
        self.dateEdit.setDateTime(QtCore.QDateTime(QtCore.QDate(year, month, day)))
        # print(year, month, day)

    def connect_my_sql(self, command):
        try:
            con = mysql.connector.connect(host=self.server_cent,
                                          user=self.username_sql,
                                          password=self.password_sql,
                                          database="asterisk")
            cur = con.cursor()
            cur.execute(command)
            result = cur.fetchall()
            con.commit()
        except mysql.connector.Error:
            message = 'Ошибка БД'
            self.alert_message(message)
        return result

    def insert_data_sql(self, command1, command2):
        try:
            con = mysql.connector.connect(host=self.server_cent,
                                          user=self.username_sql,
                                          password=self.password_sql,
                                          database="asterisk")
            cur = con.cursor()
            cur.executemany(command1, command2)
            con.commit()
            # print(con)
        except mysql.connector.Error as message:
            self.alert_message(message)

    def check_num(self):
        check_num_sql = """
        SELECT max(src) as src FROM asterisk.cdr
        """
        last_num = self.connect_my_sql(check_num_sql)
        last_num = re.findall(r'\d+', str(last_num))
        last_num = int(last_num[0])
        new_num = last_num + 1

        return new_num

    def start_all(self):
        if len(self.lineEdit.text()) < 1:
            message = 'Выберете файл.'
            self.alert_message(message)
            return
        if self.radioButton_2.isChecked() is True:
            self.upload_csv(self.bd_ul)
            self.create_file_ul()
            self.copy_files()
            return
        self.upload_csv(self.bd_fiz)
        self.create_file()
        self.copy_files()
        self.timer.start(10000)

    def create_file_ul(self):
        with open(self.lineEdit.text(), 'rt') as f:
            lines = f.readlines()
            f.close()
        new_num = self.check_num()
        context = 'obzvon-ul'
        # print(new_num)
        for i in range(len(lines)):
            item = lines[i].strip().split(';')
            num = new_num
            lic = item[0]
            number = item[1]
            summa = item[2]
            file_data = f'Channel: Local/{number}@prozvon-dialer\nMaxRetries: 2\nRetryTime: 3600\n' \
                        f'WaitTime: 40\nContext: {context}\nExtension: 401\nCallerid: {num}\nAccount: {lic}\n' \
                        f'Priority: 1\nSetvar: lic={lic}\nSetVar: number={number}\nSetVar: num={num}\nSetVar: summa={summa}'
            dir_tmp = os.path.exists(local_path_file)
            if dir_tmp is False:
                os.mkdir(local_path_file)
            new_file = local_path_file + str(lic)
            with open(new_file, 'w') as f:
                f.write(file_data)
                f.close()
                # print('DONE')

    def upload_csv(self, bd):
        with open(self.lineEdit.text(), 'rt') as f:
            lines = f.readlines()
            f.close()
        new_num = self.check_num()                      # Проверка последнего номера в CDR и получаем следующий
        already_num = f"""
        SELECT max(num) as num FROM {bd}
        """
        last_num = self.connect_my_sql(already_num)     # Проверка последнего номера в таблице obzvon
        last_num = re.findall(r'\d+', str(last_num))
        last_num = int(last_num[0])
        if new_num == last_num:                         # Если номера совпадают стираем предыдущие записи с таким номером
            print("Вы уже загрузили, но не звонили")
            delete_last = f"""DELETE FROM {bd} where num = {last_num};"""
            self.connect_my_sql(delete_last)
            print(delete_last)
        # print(new_num)
        num = []
        lic = []
        number = []
        summa = []
        for i in range(len(lines)):
            item = lines[i].strip().split(';')
            num.append(new_num)
            lic.append(item[0])
            number.append(item[1])
            summa.append(item[2])
        value_records = [(num[i], lic[i], number[i], summa[i]) for i in range(len(num))]
        export_data = f"""
                INSERT INTO {bd} (num, lic, number, summa)
                VALUES(%s, %s, %s, %s)
                """
        self.insert_data_sql(export_data, value_records)

    def create_file(self):
        context = 'prozvon-informer4'
        num_now = self.check_num()
        select_num = """
        select obzvon.lic as lic,
        obzvon.num as num,
        obzvon.number as number,
        obzvon.summa as summa,
        np.n1 as np,
        ul.n1 as ul,
        case when lics.dom=0 then '' else lics.dom end as dom,
        coalesce(domlit.n1,'') as domlit,
        case when lics.kv= 0 then '' else lics.kv end as kv,
        coalesce(kvlit.n1,'') as kvlit from asterisk.obzvon_number as obzvon
        left outer join asterisk.lics as lics on obzvon.lic=lics.lic left outer join asterisk.np as np on lics.np=np.n
        left outer join asterisk.ul as ul on lics.ul=ul.n left outer join asterisk.domlit as domlit on lics.domlit=domlit.n
        left outer join asterisk.kvlit as kvlit on lics.kvlit=kvlit.n
        where obzvon.number is not null and obzvon.num={0};
        """.format(num_now)

        num_now = self.connect_my_sql(select_num)
        files_count = 0
        for i in num_now:
            lic = i[0]
            num = i[1]
            number = i[2]
            summa = i[3]
            np = i[4]
            file_data = f'Channel: Local/{number}@prozvon-dialer\nMaxRetries: 2\nRetryTime: 3600\n' \
                        f'WaitTime: 40\nContext: {context}\nExtension: 400\nCallerid: {num}\nAccount: {lic}\n' \
                        f'Priority: 1\nSetvar: lic={lic}\nSetVar: number={number}\nSetVar: num={num}\n'
            if np is not None:
                if len(np) > 1:
                    file_data = file_data + f'SetVar: np={np}\n'
            ul = i[5]
            if ul is not None:
                if len(ul) > 1:
                    file_data = file_data + f'SetVar: ul={ul}\n'
            dom = i[6]
            if dom is not None:
                if len(dom) >= 1:
                    file_data = file_data + f'SetVar: dom={dom}\n'
            domlit = i[7]
            if domlit is not None:
                if len(domlit) >= 1:
                    file_data = file_data + f'SetVar: domlit={domlit}\n'
            kv = i[8]
            if kv is not None:
                if len(kv) >= 1:
                    file_data = file_data + f'SetVar: kv={kv}\n'
            kvlit = i[9]
            if kvlit is not None:
                if len(kvlit) >= 1:
                    file_data = file_data + f'SetVar: kvlit={kvlit}\n'
            file_data = file_data + f'SetVar: summa={summa}'
            dir_tmp = os.path.exists(local_path_file)
            if dir_tmp is False:
                os.mkdir(local_path_file)
            new_file = local_path_file + str(lic)
            with open(new_file, 'w') as f:
                f.write(file_data)
                f.close()
                # print('DONE')
            files_count += 1
        # print(files_count)

    def copy_files(self):  # Копирование файлов на сервер ДОБАВИть проверку времени старта
        file_list = os.listdir(local_path_file)
        if len(file_list) < 1:
            message = 'Что-то пошло не так. Файлы не созданы'
            self.alert_message(message)
            return
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.server_cent, username=self.username_cent, password=self.password_cent)
        next_day = self.ring_in_day
        day_ring = day
        if hour > 12:
            message = 'Уже поздно звонить, начнём завтра.'
            self.alert_message(message)
            # print('Уже поздно звонить')
            day_ring = day_ring + 1

        for i, file in enumerate(file_list):
            # print(file_list[i])
            new_local_path_file = local_path_file + file_list[i]
            new_remote_path = remote_path + '/' + file_list[i]
            sftp = ssh.open_sftp()
            sftp.put(new_local_path_file, new_remote_path)
            sftp.close()
            new_file = file_list[i]
            if i > next_day:
                day_ring = day_ring + 1
                next_day = next_day + self.ring_in_day
            yy = str(year)[-2:]
            if len(str(month)) == 1:
                month_new = f'0{month}'
            if len(str(day_ring)) == 1:
                day_ring = f'0{day_ring}'
            command_change_date = f'touch -t {yy}{month_new}{day_ring}1000.00 {remote_path}/{new_file}'
            # print(command_change_date)
            stdin, stdout, stderr = ssh.exec_command(command_change_date)
            errs = stderr.read()
            if errs:
                raise Exception('failed {0}'.format(errs))
            os.remove(f'{local_path_file}{new_file}')
        # print('OK')
        command_count = 'ls ' + remote_path + '* | wc -l'
        command_chown = 'chown -R asterisk:asterisk ' + remote_path
        command_chmod = 'chmod -R 777 ' + remote_path
        command_mv = 'mv ' + remote_path + '/* ' + remote_path_end
        stdin, stdout, stderr = ssh.exec_command(command_count)
        errs = stderr.read()
        if errs:
            raise Exception('failed {0}'.format(errs))
        count_files = re.findall(r'\d+', str(stdout.read()))
        count_files = int(count_files[0])
        # print(count_files)
        stdin, stdout, stderr = ssh.exec_command(command_chown)
        errs = stderr.read()
        if errs:
            raise Exception('failed {0}'.format(errs))
        stdin, stdout, stderr = ssh.exec_command(command_chmod)
        errs = stderr.read()
        if errs:
            raise Exception('failed {0}'.format(errs))

        stdin, stdout, stderr = ssh.exec_command(command_mv)
        errs = stderr.read()
        if errs:
            raise Exception('failed {0}'.format(errs))
        ssh.close()
        if int(count_files) != len(file_list):
            print('Не все файлы скопированы')
            not_copy = len(file_list) - int(count_files)
            message = '!!! Не скопировано файлов: ' + str(not_copy)
            self.alert_message(message)
        self.label_all.setText(str(count_files))
        self.timer.timeout.connect(self.stat_call)
        self.stat_call()
        self.timer.start(10000)

    def stat_call(self):

        def timer_thread(obj):
            check_called = """
                    SELECT count(*) FROM asterisk.cdr
                    where year(calldate) = {0}
                    and month(calldate) = {1}
                    and day(calldate) = {2}
                    """.format(year, month, day)
            check_answer = """
                    SELECT count(*) FROM asterisk.cdr
                    where year(calldate) = {0}
                    and month(calldate) = {1}
                    and day(calldate) = {2}
                    and disposition = 'ANSWERED'
                    """.format(year, month, day)
            called_count = self.connect_my_sql(check_called)
            called_count = re.findall(r'\d+', str(called_count))
            called_count = int(called_count[0])
            # print(called_count)
            called_answer = self.connect_my_sql(check_answer)
            called_answer = re.findall(r'\d+', str(called_answer))
            called_answer = int(called_answer[0])
            # print(called_answer)
            self.label_success.setText(str(called_answer))
            self.label_try.setText(str(called_count))

        threading.Thread(target=timer_thread, args=(self,)).start()

    # def create_wav(self):
    #     command_release_lic = """
    #     update asterisk.obzvon_ul as u1
    #     join asterisk.obzvon_ul as u2 on u2.id=u1.id
    #     set u1.lic_wav=insert(insert(insert(insert(u2.lic,10,0,' '),8,0,' '),6,0,' '),4,0,' ');
    #     """
    #     self.connect_my_sql(command_release_lic)

    def date_change(self):
        date_start = self.dateEdit_2.date()
        date_end = self.dateEdit_3.date()
        self.day_start = date_start.day()
        self.month_start = date_start.month()
        self.year_start = date_start.year()
        self.day_end = date_end.day()
        self.month_end = date_end.month()
        self.year_end = date_end.year()
        # print(date_start, date_end)

    def load_report(self):
        command = f"""
        SELECT accountcode as ls, dst as tel, count(*) as try, 
        case when sum(billsec)  = 0 then 0 else 1 end as answer,
        sum(billsec) as sec, max(summa) as summa
        FROM asterisk.cdr cdr 
        left outer join asterisk.obzvon_number obz on 
        obz.num = cdr.src and obz.lic = cdr.accountcode
        where calldate >= '{self.year_start}-{self.month_start}-{self.day_start}'
        and calldate <= '{self.year_end}-{self.month_end}-{self.day_end}'
        group by  accountcode, dst
        order by count(*);
        """
        calls = self.connect_my_sql(command)
        headers = ['Лицевой', 'Номер телефона', 'Попыток', 'Успешных дозвонов', 'Время разговора', 'Сумма задолжности']
        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(headers)
        for row_number, call in enumerate(calls):
            table_item = []
            model.insertRow(row_number)
            for value in call:
                item = QtGui.QStandardItem(str(value))
                table_item.append(item)
            model.insertRow(row_number, table_item)
        self.tableView.setModel(model)
        self.calls = calls

    def save_xlsx(self, calls):

        with xlsxwriter.Workbook(f'{local_path}/Отчёт'
                                 f'{self.year_start}'
                                 f'{self.month_start}'
                                 f'{self.day_end}.xlsx') as workbook:
            worksheet = workbook.add_worksheet()
            worksheet.set_column('A:A', 15)
            worksheet.set_column('B:B', 18)
            worksheet.set_column('C:C', 10)
            worksheet.set_column('D:D', 18)
            worksheet.set_column('E:E', 18)
            worksheet.set_column('F:F', 18)
            worksheet.write('A1', 'Лицевой')
            worksheet.write('B1', 'Номер телефона')
            worksheet.write('C1', 'Попыток')
            worksheet.write('D1', 'Успешных дозвонов')
            worksheet.write('E1', 'Время разговора')
            worksheet.write('F1', 'Сумма задолжности')
            for row_number, call in enumerate(calls):
                for value, values in enumerate(call):
                    worksheet.write(row_number + 1, value, values)
        self.alert_message(f'Файл создан, сохранено {len(calls)} записей')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ParentWindow()
    window.show()
    app.exec()
