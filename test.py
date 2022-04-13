from cgi import print_exception
import time, random, math
from enum import Enum
from adhoccomputing import GenericModel, GenericEvent, Generics, Definitions, Topology, FrameHandlerBase, UsrpB210OfdmFlexFramePhy
from LiquidDsputils import *
from Uhdutils import *
from ctypes import *

import queue
import pickle
# from ahc import ComponentModel, Event, ConnectorTypes, Topology, EventTypes, GenericMessage, GenericMessageHeader, FramerObjects
# from ahc import ComponentRegistry
# from ahc.PhysicalLayers.UsrpB210OfdmFlexFramePhy import  UsrpB210OfdmFlexFramePhy
# from ahc.MAC.CSMA import MacCsmaPPersistent,MacCsmaPPersistentConfigurationParameter

class FramerObjects():
    framerobjects = {}
    ahcuhdubjects = {}
    def add_framer(self, id, obj):
        self.framerobjects[id] = obj

    def get_framer_by_id(self, id):
        return self.framerobjects[id]

    def add_ahcuhd(self, id, obj):
        self.ahcuhdubjects[id] = obj

    def get_ahcuhd_by_id(self, id):
        return self.ahcuhdubjects[id]



framers = FramerObjects()


# define your own message types
class ApplicationLayerMessageTypes(Enum):
    BROADCAST = "BROADCAST"


# define your own message header structure
class ApplicationLayerMessageHeader(Generics.GenericMessageHeader):
    pass


class UsrpApplicationLayerEventTypes(Enum):
    STARTBROADCAST = "startbroadcast"


class UsrpApplicationLayer(GenericModel):
    # def on_init(self, eventobj: GenericEvent):

    def __init__(self, componentname, componentid):
        super().__init__(componentname, componentid)
        self.counter = 0
        self.eventhandlers[UsrpApplicationLayerEventTypes.STARTBROADCAST] = self.on_startbroadcast

    def on_message_from_top(self, eventobj: GenericEvent):
    # print(f"I am {self.componentname}.{self.componentinstancenumber},sending down eventcontent={eventobj.eventcontent}\n")
        self.send_down(GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent))

    def on_message_from_bottom(self, eventobj: GenericEvent):
        evt = GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
        print(f"I am Node.{self.componentinstancenumber}, received from Node.{eventobj.eventcontent.header.messagefrom} a message: {eventobj.eventcontent.payload}")
        if self.componentinstancenumber == 1:
            evt.eventcontent.header.messageto = 0
            evt.eventcontent.header.messagefrom = 1
        else:
            evt.eventcontent.header.messageto = 1
            evt.eventcontent.header.messagefrom = 0
        evt.eventcontent.payload = eventobj.eventcontent.payload
        #print(f"I am {self.componentname}.{self.componentinstancenumber}, sending down eventcontent={eventobj.eventcontent.payload}\n")
        self.send_down(evt)  # PINGPONG

    def on_startbroadcast(self, eventobj: GenericEvent):
        if self.componentinstancenumber == 1:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 1, 0)
        else:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 0, 1)
        self.counter = self.counter + 1

        payload = "BMSG-" + str(self.counter)
        broadcastmessage = Generics.GenericMessage(hdr, payload)
        evt = GenericEvent(self, Definitions.EventTypes.MFRT, broadcastmessage)
        # time.sleep(3)
        self.send_down(evt)

    def send_self(self, event: GenericEvent):
        self.trigger_event(event)

class UsrpB210PhyEventTypes(Enum):
  RECV = "recv"


# define your own message header structure
class UsrpB210PhyMessageHeader(Generics.GenericMessageHeader):
    pass


# define your own message payload structure
class UsrpB210PhyMessagePayload(Generics.GenericMessagePayload):

  def __init__(self, header, payload):
    self.phyheader = header
    self.phypayload = payload


class UsrpB210PhyMessageTypes(Enum):
  PHYFRAMEDATA = "PHYFRAMEDATA"


class ComponentConfigurationParameters():
    pass

class MacCsmaPPersistentConfigurationParameters (ComponentConfigurationParameters):
    def __init__(self, p):
        self.p = p

class GenericMacEventTypes(Enum):
    HANDLEMACFRAME = "handlemacframe"


class GenericMac(GenericModel):

    def __init__(self, componentname, componentinstancenumber, uhd):
        super().__init__(componentname, componentinstancenumber)
        self.framequeue = queue.Queue()
        self.ahcuhd = uhd
        print("I am Generic MAC my uhd instance id is ", self.ahcuhd.componentinstancenumber)
        self.eventhandlers[GenericMacEventTypes.HANDLEMACFRAME] = self.on_handlemacframe


    def on_init(self, eventobj: GenericEvent):
        self.send_self(GenericEvent(self, GenericMacEventTypes.HANDLEMACFRAME, None))  # Continuously trigger handle_frame
        print("Initialized", self.componentname, ":", self.componentinstancenumber)

    def on_handlemacframe(self, eventobj: GenericEvent):
        # print("will handle frame from on_handlemacframe")
        self.handle_frame()
        # self.send_self(Event(self, GenericMacEventTypes.HANDLEMACFRAME, None)) #Continuously trigger handle_frame
        # HANDLEMACFRAME event will be generated by the inheriting component to facilitate delay

    def on_message_from_bottom(self, eventobj: GenericEvent):
        # print(f"I am {self.componentname}, eventcontent={eventobj.eventcontent}\n")
        evt = GenericEvent(self, Definitions.EventTypes.MFRB, eventobj.eventcontent)
        self.send_up(evt)

    def on_message_from_top(self, eventobj: GenericEvent):
        # print(f"I am {self.componentname}, eventcontent={eventobj.eventcontent}\n")
        # put message in queue and try accessing the channel
        # self.on_handlemacframe(eventobj)
        self.framequeue.put_nowait(eventobj)
        self.handle_frame()
        #print("Mac put the frame in queueu", eventobj.eventcontent.payload)

    def handle_frame(self):
        pass

class MacCsmaPPersistent(GenericMac):

    #Constructor
    def __init__(self, componentname, componentinstancenumber, configurationparameters:MacCsmaPPersistentConfigurationParameters, uhd):
        super().__init__(componentname, componentinstancenumber, uhd)
        self.p = configurationparameters.p

    #on_init will be called from topo.start to initialize components
    def on_init(self, eventobj: GenericEvent):
        self.retrialcnt = 0
        super().on_init(eventobj)  # required because of inheritence
        #print("Initialized", self.componentname, ":", self.componentinstancenumber)

    def send_self(self, event: GenericEvent):
        self.trigger_event(event)

    def handle_frame(self):
        #TODO: not a good solution put message in queue, schedule a future event to retry yhe first item in queueu
        # print("handle_frame")
        if self.framequeue.qsize() > 0:
            randval = random.random()
            if randval < self.p: # TODO: Check if correct
                clearmi, powerdb  = self.ahcuhd.ischannelclear(threshold=-35)
                #print("Component:", self.componentinstancenumber, "clear mi=", clearmi, " Power=", powerdb)
                if  clearmi == True:
                    try:
                        eventobj = self.framequeue.get()
                        evt = GenericEvent(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
                        self.send_down(evt)
                        self.retrialcnt = 0
                    except Exception as e:
                        raise(e)
                        print("MacCsmaPPersistent handle_frame exception, ")
                else:
                    self.retrialcnt = self.retrialcnt + 1
                    time.sleep(random.randrange(0,math.pow(2,self.retrialcnt))*0.001)
                    #print("Busy")
        else:
            #print("Queue size", self.framequeue.qsize())
            pass
        time.sleep(0.00001) # TODO: Think about this otherwise we will only do cca
        self.send_self(GenericEvent(self, GenericMacEventTypes.HANDLEMACFRAME, None)) #Continuously trigger handle_frame


class UsrpNode(GenericModel):
    counter = 0
    def on_init(self, eventobj: GenericEvent):
        pass

    def __init__(self, componentname, componentid):
        # SUBCOMPONENTS

        macconfig = MacCsmaPPersistentConfigurationParameters(0.5)

        self.appl = UsrpApplicationLayer("UsrpApplicationLayer", componentid)
        self.phy = UsrpB210OfdmFlexFramePhy("UsrpB210OfdmFlexFramePhy", componentid)
        self.mac = MacCsmaPPersistent("MacCsmaPPersistent", componentid,  configurationparameters=macconfig,uhd=self.phy.ahcuhd)

        # CONNECTIONS AMONG SUBCOMPONENTS
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.UP, self) #Not required if nodemodel will do nothing
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.mac)

        self.mac.connect_me_to_component(Definitions.ConnectorTypes.UP, self.appl)
        self.mac.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.phy)

        # Connect the bottom component to the composite component....
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.UP, self.mac)
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self)

        # self.phy.connect_me_to_component(ConnectorTypes.DOWN, self)
        # self.connect_me_to_component(ConnectorTypes.DOWN, self.appl)

        super().__init__(componentname, componentid)

def main():
    topo = Topology()
# Note that the Topology has to specific: usrp winslab_b210_0 is run by instance 0 of the component
# Therefore, the usrps have to have names winslab_b210_x where x \in (0 to nodecount-1)
    topo.construct_winslab_topology_without_channels(4, UsrpNode)
  # topo.construct_winslab_Topology_with_channels(2, UsrpNode, FIFOBroadcastPerfectChannel)

  # time.sleep(1)
  # topo.nodes[0].send_self(Event(topo.nodes[0], UsrpNodeEventTypes.STARTBROADCAST, None))

    topo.start()
    i = 0
    while(i < 10):
        topo.nodes[1].appl.send_self(GenericEvent(topo.nodes[0], UsrpApplicationLayerEventTypes.STARTBROADCAST, None))
        time.sleep(1)
        i = i + 1


if __name__ == "__main__":
    main()