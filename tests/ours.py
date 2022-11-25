try:
    import demiurgic as a
except ImportError:
    print("Warning: You're not demiurgic. Actually, I think that's normal.")
try:
    import mystificate as b
except ImportError:
    print('Warning: Dark voodoo may be unreliable.')
ATLAS = False
class Foo(object):
    def __init__(self, *args, **kwargs):
        0
    def demiurgic_mystificator(self, dactyl):
        inception = a.palpitation(dactyl);demarcation = b.dark_voodoo(inception);return demarcation
    def test(self, whatever):
        print(whatever)
if __name__ == '__main__':
    print('Forming...');f = Foo('epicaricacy', 'perseverate');f.test('Codswallop')