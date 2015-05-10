import argparse


class RegisterLeafClasses(type):
    def __init__(cls, name, bases, nmspc):
        super(RegisterLeafClasses, cls).__init__(name, bases, nmspc)
        if not hasattr(cls, 'registry'):
            cls.registry = set()
        cls.registry.add(cls)
        cls.registry -= set(bases) # Remove base classes

    # Metamethods, called on class objects:
    def __iter__(cls):
        return iter(cls.registry)

    def __str__(cls):
        if cls in cls.registry:
            return cls.__name__
        return cls.__name__ + " leaf classes: " + ", ".join([sc.__name__ for sc in cls])


class Plugin(object, metaclass=RegisterLeafClasses):
    """Plugin base class. May be subject to changes."""
    MIN_VERSION = None
    MAX_VERSION = None

    @classmethod
    def check_version(cls, version: str) -> bool:
        from distutils.version import LooseVersion
        if cls.MIN_VERSION:
            if LooseVersion(cls.MIN_VERSION) > LooseVersion(version):
                return False
        if cls.MAX_VERSION:
            return LooseVersion(cls.MAX_VERSION) >= LooseVersion(version)
        return True

    @classmethod
    def __str__(cls):
        return cls.__name__

    @staticmethod
    def attach(subparsers: argparse.ArgumentParser, log: list, **kwargs):
        pass

    @staticmethod
    def action(args: argparse.Namespace):
        pass