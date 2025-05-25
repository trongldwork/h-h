from collections import deque
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from threading import Lock
import time
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# So luong ve ban dau
TICKETS = 50
tickets_left = TICKETS

# Cau hinh hang ghe
ROWS = 10  # M hang
COLS = 20  # N cot
TOTAL_SEATS = ROWS * COLS


# ======== PRIMITIVE SEMAPHORE IMPLEMENTATION ===========
class PrimitiveSemaphore:
    def __init__(self, initial_value: int):
        self.value = initial_value
        self.waiting_queue = deque()  # Mô phỏng S.Ptr
        self._lock = threading.Lock()

    def P(self):
        with self._lock:
            self.value -= 1
            if self.value < 0:
                event = threading.Event()
                self.waiting_queue.append(event)
                # Thoát lock trước khi block để tránh deadlock
                self._lock.release()
                event.wait()  # block()
                self._lock.acquire()

    def P_non_blocking(self):
        with self._lock:
            if self.value > 0:
                self.value -= 1
                return True
            return False

    def V(self):
        with self._lock:
            self.value += 1
            if self.value <= 0 and self.waiting_queue:
                event = self.waiting_queue.popleft()
                event.set()  # wakeup()

    def get_value(self):
        return self.value


# Cac cau truc dong bo cho ve
mutex = Lock()
primitive_sema = PrimitiveSemaphore(TICKETS)  # Su dung primitive semaphore
spinlock_flag = False

# Cac ma tran ghe cho tung phuong phap dong bo
# 0 = trong, 1 = da dat
mutex_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]
semaphore_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]
spinlock_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]

# Ma tran cac mutex rieng biet cho tung ghe (fine-grained locking)
seat_mutexes = [[Lock() for _ in range(COLS)] for _ in range(ROWS)]

# Ma tran cac primitive semaphore rieng biet cho tung ghe
seat_primitive_semaphores = [[PrimitiveSemaphore(1) for _ in range(COLS)] for _ in range(ROWS)]

# Ma tran cac spinlock rieng biet cho tung ghe
seat_spinlock_flags = [[False for _ in range(COLS)] for _ in range(ROWS)]


# ======== API: RESET VE VA GHE ===========
@app.post("/reset")
def reset_tickets():
    global tickets_left, primitive_sema, spinlock_flag, mutex_seats, semaphore_seats, spinlock_seats
    global seat_primitive_semaphores, seat_spinlock_flags
    
    # Reset ve
    tickets_left = TICKETS
    primitive_sema = PrimitiveSemaphore(TICKETS)
    spinlock_flag = False
    
    # Reset ghe
    mutex_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    semaphore_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    spinlock_seats = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    
    # Reset cac primitive semaphore rieng biet cho tung ghe
    seat_primitive_semaphores = [[PrimitiveSemaphore(1) for _ in range(COLS)] for _ in range(ROWS)]
    seat_spinlock_flags = [[False for _ in range(COLS)] for _ in range(ROWS)]
    
    return {"msg": f"Reset so ve ve {TICKETS} va tat ca ghe ({ROWS}x{COLS}) voi primitive P(S)/V(S)"}


# ======== API: MUA VE DUNG MUTEX ===========
@app.post("/buy-ticket/mutex")
def buy_ticket_mutex():
    global tickets_left
    with mutex:
        if tickets_left > 0:
            tickets_left -= 1
            return {"status": "success", "msg": f"Mua thanh cong. Con {tickets_left} ve."}
        else:
            return {"status": "fail", "msg": "Het ve."}


# ======== API: MUA VE DUNG SEMAPHORE (Primitive P/V) ===========
@app.post("/buy-ticket/semaphore")
def buy_ticket_semaphore():
    global tickets_left
    # Su dung P(S) - non-blocking version
    if primitive_sema.P_non_blocking():
        if tickets_left > 0:
            tickets_left -= 1
            return {"status": "success", "msg": f"Mua thanh cong (P/V semaphore). Con {tickets_left} ve. Semaphore value: {primitive_sema.get_value()}"}
        else:
            primitive_sema.V()  # Giai phong lai
            return {"status": "fail", "msg": "Het ve (P/V semaphore) - inconsistency detected."}
    else:
        return {"status": "fail", "msg": f"Het ve (P/V semaphore). Semaphore value: {primitive_sema.get_value()}"}


# ======== API: MUA VE DUNG SPINLOCK (test-and-set) ===========
def test_and_set():
    global spinlock_flag
    if not spinlock_flag:
        spinlock_flag = True
        return False
    return True

def release_spinlock():
    global spinlock_flag
    spinlock_flag = False

@app.post("/buy-ticket/spinlock")
def buy_ticket_spinlock():
    global tickets_left

    # Cho den khi vao duoc vung critical
    while test_and_set():
        time.sleep(0.001)

    result = {}
    if tickets_left > 0:
        tickets_left -= 1
        result = {"status": "success", "msg": f"Mua thanh cong (spinlock). Con {tickets_left} ve."}
    else:
        result = {"status": "fail", "msg": "Het ve (spinlock)."}

    release_spinlock()
    return result


# ======== API: DAT GHE DUNG MUTEX (Fine-grained per seat) ===========
@app.post("/book-seat/mutex/{row}/{col}")
def book_seat_mutex(row: int, col: int):
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return {"status": "fail", "msg": "Vi tri ghe khong hop le."}
    
    # Su dung mutex rieng biet cho ghe nay
    with seat_mutexes[row][col]:
        if mutex_seats[row][col] == 0:
            mutex_seats[row][col] = 1
            return {"status": "success", "msg": f"Dat ghe thanh cong (mutex-per-seat): hang {row+1}, cot {col+1}"}
        else:
            return {"status": "fail", "msg": f"Ghe da duoc dat (mutex-per-seat): hang {row+1}, cot {col+1}"}

# ======== API: DAT GHE DUNG SEMAPHORE (Pure P/V operations) ===========
@app.post("/book-seat/semaphore/{row}/{col}")
def book_seat_semaphore(row: int, col: int):
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return {"status": "fail", "msg": "Vi tri ghe khong hop le."}
    
    # Su dung primitive P(S) operation
    if seat_primitive_semaphores[row][col].P_non_blocking():
        # P(S) thanh cong - ghe da duoc "acquire"
        semaphore_seats[row][col] = 1  # Danh dau visual
        return {"status": "success", "msg": f"Dat ghe thanh cong (P/V): hang {row+1}, cot {col+1}"}
    else:
        # P(S) that bai - ghe da duoc dat
        return {"status": "fail", "msg": f"Ghe da duoc dat (P/V): hang {row+1}, cot {col+1}"}

# ======== API: DAT GHE DUNG SPINLOCK (Pure test-and-set) ===========
def test_and_set_seat(row: int, col: int):
    """Pure test-and-set cho ghe cu the - ATOMIC operation"""
    # Gia lap atomic test-and-set bang cach doc va ghi trong 1 buoc
    old_value = seat_spinlock_flags[row][col]
    seat_spinlock_flags[row][col] = True
    return old_value

@app.post("/book-seat/spinlock/{row}/{col}")
def book_seat_spinlock(row: int, col: int):
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return {"status": "fail", "msg": "Vi tri ghe khong hop le."}
    
    # Pure spinlock - chi dung test-and-set
    while test_and_set_seat(row, col):
        time.sleep(0.001)  # Spin wait
    
    # Da vao duoc critical section
    try:
        if spinlock_seats[row][col] == 0:
            spinlock_seats[row][col] = 1
            result = {"status": "success", "msg": f"Dat ghe thanh cong (pure-spinlock): hang {row+1}, cot {col+1}"}
        else:
            result = {"status": "fail", "msg": f"Ghe da duoc dat (pure-spinlock): hang {row+1}, cot {col+1}"}
    finally:
        # Reset flag de giai phong
        seat_spinlock_flags[row][col] = False
    
    return result

# ======== API: GIAI PHONG GHE (V operation) ===========
@app.post("/release-seat/semaphore/{row}/{col}")
def release_seat_semaphore(row: int, col: int):
    if row < 0 or row >= ROWS or col < 0 or col >= COLS:
        return {"status": "fail", "msg": "Vi tri ghe khong hop le."}
    
    if semaphore_seats[row][col] == 1:
        # Su dung V(S) operation de giai phong ghe
        seat_primitive_semaphores[row][col].V()
        semaphore_seats[row][col] = 0  # Cap nhat visual
        return {"status": "success", "msg": f"Giai phong ghe thanh cong (V): hang {row+1}, cot {col+1}"}
    else:
        return {"status": "fail", "msg": f"Ghe chua duoc dat: hang {row+1}, cot {col+1}"}

# ======== API: XEM TRANG THAI GHE ===========
@app.get("/seats/mutex")
def get_mutex_seats():
    available = sum(row.count(0) for row in mutex_seats)
    booked = TOTAL_SEATS - available
    return {
        "method": "mutex",
        "seats": mutex_seats,
        "available": available,
        "booked": booked,
        "total": TOTAL_SEATS
    }

@app.get("/seats/semaphore") 
def get_semaphore_seats():
    available = sum(row.count(0) for row in semaphore_seats)
    booked = TOTAL_SEATS - available
    return {
        "method": "semaphore",
        "seats": semaphore_seats,
        "available": available,
        "booked": booked,
        "total": TOTAL_SEATS
    }

@app.get("/seats/spinlock")
def get_spinlock_seats():
    available = sum(row.count(0) for row in spinlock_seats)
    booked = TOTAL_SEATS - available
    return {
        "method": "spinlock", 
        "seats": spinlock_seats,
        "available": available,
        "booked": booked,
        "total": TOTAL_SEATS
    }

@app.get("/seats/config")
def get_seats_config():
    return {
        "rows": ROWS,
        "cols": COLS,
        "total_seats": TOTAL_SEATS
    }


# ======== API: LAY TRANG THAI HIEN TAI ===========
@app.get("/status")
def get_status():
    mutex_available_seats = sum(row.count(0) for row in mutex_seats)
    semaphore_available_seats = sum(row.count(0) for row in semaphore_seats)
    spinlock_available_seats = sum(row.count(0) for row in spinlock_seats)
    
    # Dem so semaphore available seats bang cach kiem tra gia tri semaphore
    primitive_sem_available = sum(
        seat_primitive_semaphores[row][col].get_value() 
        for row in range(ROWS) 
        for col in range(COLS)
    )
    
    return {
        "tickets_left": tickets_left,
        "semaphore_tickets_left": primitive_sema.get_value(),
        "seats_config": {"rows": ROWS, "cols": COLS, "total": TOTAL_SEATS},
        "available_seats": {
            "mutex": mutex_available_seats,
            "semaphore": semaphore_available_seats,
            "semaphore_primitive_count": primitive_sem_available,
            "spinlock": spinlock_available_seats
        }
    }
