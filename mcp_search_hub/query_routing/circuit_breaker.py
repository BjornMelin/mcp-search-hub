"""Circuit breaker implementation for provider protection."""

import time


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting providers from cascading failures.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Failing, all requests are blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(self, max_failures: int = 3, reset_timeout: float = 30.0):
        """
        Initialize circuit breaker.

        Args:
            max_failures: Maximum failures before circuit opens
            reset_timeout: Time in seconds before attempting reset
        """
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = "closed"  # closed, open, half-open
        self._reset_triggered = False

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open (blocking requests)."""
        if self.state == "closed":
            return False

        # Check if timeout has passed for potential reset
        if (
            self.last_failure_time
            and time.time() - self.last_failure_time > self.reset_timeout
        ):
            self.state = "half-open"
            self._reset_triggered = True

        return self.state == "open"

    @property
    def is_half_open(self) -> bool:
        """Check if circuit breaker is in half-open state (testing recovery)."""
        return self.state == "half-open"

    def record_success(self):
        """Record successful execution."""
        if self.state == "half-open":
            # Successful request during half-open state means recovery
            self.state = "closed"
            self._reset_triggered = False
        self.failure_count = 0

    def record_failure(self):
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        # Check if we should open the circuit
        if self.failure_count >= self.max_failures:
            self.state = "open"
            self._reset_triggered = False

        # If in half-open state and still failing, go back to open
        if self.state == "half-open":
            self.state = "open"
            self._reset_triggered = False

    def get_state(self) -> str:
        """Get current circuit breaker state."""
        # Update state based on timeout if needed
        if (
            self.state == "open"
            and self.last_failure_time
            and time.time() - self.last_failure_time > self.reset_timeout
        ):
            self.state = "half-open"
            self._reset_triggered = True

        return self.state

    def reset(self):
        """Manually reset the circuit breaker."""
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = None
        self._reset_triggered = False
