python3.11 -m venv venv                                              
source venv/bin/activate
docker-compose up -d
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

cd codezen-web
python3 -m http.server 5500

http://localhost:5500