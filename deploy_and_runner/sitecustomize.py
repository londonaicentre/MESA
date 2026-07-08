import vllm.platforms.interface as interface


class WSLUvaPatch:

    @staticmethod
    def apply() -> None:
        # wsl cuda fix
        interface.in_wsl = lambda: False


WSLUvaPatch.apply()
