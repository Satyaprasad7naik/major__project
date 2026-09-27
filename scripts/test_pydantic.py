import pydantic
print(f"Pydantic version: {pydantic.__version__}")
try:
    from pydantic import BaseModel
    class Test(BaseModel):
        name: str
    t = Test(name="test")
    print(f"Pydantic model OK: {t}")
except Exception as e:
    print(f"Pydantic failed: {e}")
