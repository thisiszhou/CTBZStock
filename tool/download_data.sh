cd /c/Users/Administrator/Desktop/stock/CTBZStock
cd main/update_data
python online_update.py &> update_data.log

cd /c/Users/Administrator/Desktop/stock/CTBZStock
cd main/back_test
python run.py &> back_test.log
