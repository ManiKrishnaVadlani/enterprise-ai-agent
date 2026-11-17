from app.limits import UploadConcurrencyLimit, UserRateLimiter


def test_user_rate_limiter_is_per_user_and_expires_old_requests():
    limiter = UserRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.consume("alice", now=100) is None
    assert limiter.consume("alice", now=101) is None
    assert limiter.consume("alice", now=102) == 8
    assert limiter.consume("bob", now=102) is None
    assert limiter.consume("alice", now=111) is None


def test_user_rate_limiter_bounds_tracked_users():
    limiter = UserRateLimiter(max_requests=1, window_seconds=10, max_tracked_users=1)
    assert limiter.consume("alice", now=100) is None
    assert limiter.consume("bob", now=100) == 10


def test_upload_concurrency_limit_times_out_and_releases():
    limiter = UploadConcurrencyLimit(1, 0.01)
    assert limiter.acquire()
    assert limiter.acquire() is False
    limiter.release()
    assert limiter.acquire()
    limiter.release()
